"""Coordinator: fetches the hourly forecast and evaluates every period."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from astral import sun as astral_sun
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfLength,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.sun import get_astral_observer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import (
    DistanceConverter,
    SpeedConverter,
    TemperatureConverter,
)

from .const import (
    CONF_WEATHER_ENTITY,
    DOMAIN,
    MIN_UV_SUN_ELEVATION,
    SUBENTRY_PERIOD,
    SUBENTRY_RULE,
    UPDATE_INTERVAL,
)
from .rules import evaluate_period

if TYPE_CHECKING:
    from . import LayercastConfigEntry

_LOGGER = logging.getLogger(__name__)

# forecast key -> (converter, canonical unit, entity attribute holding the source unit)
_CONVERSIONS = {
    "temperature": (TemperatureConverter, UnitOfTemperature.CELSIUS, "temperature_unit"),
    "apparent_temperature": (TemperatureConverter, UnitOfTemperature.CELSIUS, "temperature_unit"),
    "wind_speed": (SpeedConverter, UnitOfSpeed.KILOMETERS_PER_HOUR, "wind_speed_unit"),
    "wind_gust_speed": (SpeedConverter, UnitOfSpeed.KILOMETERS_PER_HOUR, "wind_speed_unit"),
    "precipitation": (DistanceConverter, UnitOfLength.MILLIMETERS, "precipitation_unit"),
}
_PLAIN = ("humidity", "precipitation_probability", "uv_index", "condition")


def normalize_forecast(
    forecast: list[dict],
    attributes: dict,
    elevation: Callable[[datetime], float] | None = None,
) -> list[dict]:
    """Convert forecast items to canonical units with timezone-aware datetimes.

    With ``elevation`` (sun elevation in degrees at a time), UV of hours with a low
    sun is set to 0: a daily UV maximum repeated for every hour of the day must not
    count in the evening. A missing UV stays missing.
    """
    hours = []
    for item in forecast:
        when = dt_util.parse_datetime(item.get("datetime") or "")
        if when is None:
            continue
        hour: dict[str, Any] = {"datetime": dt_util.as_utc(when)}
        for key in _PLAIN:
            hour[key] = item.get(key)
        for key, (converter, target, unit_attr) in _CONVERSIONS.items():
            value = item.get(key)
            source = attributes.get(unit_attr)
            hour[key] = (
                converter.convert(value, source, target) if value is not None and source else value
            )
        if (
            hour["uv_index"] is not None
            and elevation is not None
            and elevation(hour["datetime"] + timedelta(minutes=30)) < MIN_UV_SUN_ELEVATION
        ):
            hour["uv_index"] = 0
        hours.append(hour)
    return hours


def rule_item(rule: dict) -> dict[str, str]:
    """What the card needs to show a matched rule."""
    item = {"name": rule["name"], "image": rule.get("image") or "generic"}
    if rule.get("image_url"):
        item["image_url"] = rule["image_url"]
    return item


class LayercastCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Evaluate all period subentries; data is keyed by subentry id."""

    config_entry: LayercastConfigEntry

    def __init__(self, hass: HomeAssistant, entry: LayercastConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL
        )
        self._weather = entry.data[CONF_WEATHER_ENTITY]
        entry.async_on_unload(
            async_track_state_change_event(hass, [self._weather], self._weather_changed)
        )

    @callback
    def _weather_changed(self, event: Event[EventStateChangedData]) -> None:
        self.config_entry.async_create_task(self.hass, self.async_request_refresh())

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        state = self.hass.states.get(self._weather)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="weather_unavailable",
                translation_placeholders={"entity": self._weather},
            )
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": self._weather, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="forecast_failed",
                translation_placeholders={"entity": self._weather, "error": str(err)},
            ) from err

        observer = get_astral_observer(self.hass)
        forecast = normalize_forecast(
            response[self._weather]["forecast"],
            dict(state.attributes),
            lambda when: astral_sun.elevation(observer, when),
        )
        entry = self.config_entry
        rules = [dict(s.data) for s in entry.get_subentries_of_type(SUBENTRY_RULE)]
        now = dt_util.now()

        data = {}
        for sub in entry.get_subentries_of_type(SUBENTRY_PERIOD):
            result = evaluate_period(forecast, dict(sub.data), rules, now)
            items = [rule_item(r) for r in result["items"]]
            state_text = ", ".join(i["name"] for i in items) or "-"
            data[sub.subentry_id] = {
                "state": state_text[:255] if result["hours"] else None,
                "attributes": {
                    "period": sub.title,
                    "start": result["start"].isoformat(),
                    "end": result["end"].isoformat(),
                    "hours": result["hours"],
                    "items": items,
                    "unsupported": [r["name"] for r in result["unsupported"]],
                    "values": result["values"],
                },
            }
        return data
