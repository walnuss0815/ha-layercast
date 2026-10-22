"""Config and subentry flows (periods and rules)."""

from __future__ import annotations

from typing import Any

import probatio as vol
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.config_entries import (
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TimeSelector,
)

from .const import (
    CONF_WEATHER_ENTITY,
    DOMAIN,
    IMAGES,
    SUBENTRY_PERIOD,
    SUBENTRY_RULE,
    WEATHER_CONDITIONS,
)
from .defaults import default_subentries


def _number(minimum: float, maximum: float, step: float, unit: str = "") -> NumberSelector:
    config = NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
    if unit:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _select(options: list[str], key: str, multiple: bool = False) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=key,
            multiple=multiple,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


WEATHER_SCHEMA = vol.Schema(
    {vol.Required(CONF_WEATHER_ENTITY): EntitySelector(EntitySelectorConfig(domain="weather"))}
)

PERIOD_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("start"): TimeSelector(),
        vol.Required("end"): TimeSelector(),
    }
)

RULE_BASICS_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("image", default="generic"): _select(IMAGES, "image"),
        vol.Optional("image_url"): str,
        vol.Optional("group"): str,
        vol.Required("priority", default=0): _number(-100, 100, 1),
    }
)

RULE_CONDITIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("temp_below"): _number(-60, 60, 0.5, "°C"),
        vol.Optional("temp_above"): _number(-60, 60, 0.5, "°C"),
        vol.Optional("temp_min_above"): _number(-60, 60, 0.5, "°C"),
        vol.Optional("feels_below"): _number(-60, 60, 0.5, "°C"),
        vol.Optional("feels_above"): _number(-60, 60, 0.5, "°C"),
        vol.Optional("rain_probability"): _number(0, 100, 1, "%"),
        vol.Optional("rain_amount"): _number(0, 200, 0.1, "mm"),
        vol.Optional("wind"): _number(0, 250, 1, "km/h"),
        vol.Optional("gusts"): _number(0, 250, 1, "km/h"),
        vol.Optional("uv"): _number(0, 15, 0.5),
        vol.Optional("humidity"): _number(0, 100, 1, "%"),
        vol.Optional("conditions"): _select(WEATHER_CONDITIONS, "weather_condition", True),
    }
)


def _supports_hourly(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    features = state.attributes.get("supported_features", 0) if state else 0
    return bool(features & WeatherEntityFeature.FORECAST_HOURLY)


def _title(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return f"Layercast {state.name if state else entity_id}"


class LayercastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Pick the weather entity; default periods and rules are created with it."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {SUBENTRY_PERIOD: PeriodSubentryFlow, SUBENTRY_RULE: RuleSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_WEATHER_ENTITY]
            await self.async_set_unique_id(entity_id)
            self._abort_if_unique_id_configured()
            if _supports_hourly(self.hass, entity_id):
                return self.async_create_entry(
                    title=_title(self.hass, entity_id),
                    data=user_input,
                    subentries=[
                        ConfigSubentryData(
                            data=data, subentry_type=kind, title=title, unique_id=None
                        )
                        for kind, title, data in default_subentries(self.hass.config.language)
                    ],
                )
            errors[CONF_WEATHER_ENTITY] = "no_hourly_forecast"
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(WEATHER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Switch to another weather entity, keeping periods and rules."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_WEATHER_ENTITY]
            other = self.hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, entity_id)
            if other and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            if _supports_hourly(self.hass, entity_id):
                return self.async_update_and_abort(
                    entry,
                    unique_id=entity_id,
                    title=_title(self.hass, entity_id),
                    data=user_input,
                )
            errors[CONF_WEATHER_ENTITY] = "no_hourly_forecast"
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(WEATHER_SCHEMA, entry.data),
            errors=errors,
        )


class PeriodSubentryFlow(ConfigSubentryFlow):
    """A named time window, like Morning 07:00-11:00."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        if user_input is not None:
            return self.async_create_entry(title=user_input["name"], data=user_input)
        return self.async_show_form(step_id="user", data_schema=PERIOD_SCHEMA)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        if user_input is not None:
            return self.async_update_and_abort(
                self._get_entry(), subentry, title=user_input["name"], data=user_input
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(PERIOD_SCHEMA, subentry.data),
        )


class RuleSubentryFlow(ConfigSubentryFlow):
    """A garment and the weather conditions it is recommended for (two steps)."""

    _basics: dict[str, Any]

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await self._basics_step("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        return await self._basics_step(
            "reconfigure", user_input, self._get_reconfigure_subentry().data
        )

    async def _basics_step(
        self, step_id: str, user_input: dict[str, Any] | None, current: Any
    ) -> SubentryFlowResult:
        if user_input is not None:
            self._basics = {**user_input, "priority": int(user_input["priority"])}
            return await self.async_step_conditions()
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(RULE_BASICS_SCHEMA, current),
        )

    async def async_step_conditions(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        reconfigure = self.source == SOURCE_RECONFIGURE
        if user_input is not None:
            data = {**self._basics, **user_input}
            if reconfigure:
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    title=data["name"],
                    data=data,
                )
            return self.async_create_entry(title=data["name"], data=data)
        current = self._get_reconfigure_subentry().data if reconfigure else {}
        return self.async_show_form(
            step_id="conditions",
            data_schema=self.add_suggested_values_to_schema(RULE_CONDITIONS_SCHEMA, current),
        )
