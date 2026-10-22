"""Shared fixtures: a mocked weather entity with an hourly forecast."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.core import HomeAssistant, SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.layercast.const import CONF_WEATHER_ENTITY, DOMAIN
from custom_components.layercast.defaults import default_subentries

WEATHER = "weather.home"
NOW = datetime(2026, 10, 22, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/layercast."""


@pytest.fixture(autouse=True)
def add_extra_js_url(hass: HomeAssistant):
    """Skip the real frontend (not installed in tests); expose the registration call."""
    hass.config.components.add("frontend")
    with patch("custom_components.layercast.add_extra_js_url") as mock:
        yield mock


def hour(h: int) -> dict:
    """Forecast for hour ``h`` of 2026-10-22 (UTC). Morning is cold, day rainy and windy."""
    item = {
        "datetime": (NOW.replace(hour=0) + timedelta(hours=h)).isoformat(),
        "temperature": 9.0,
        "precipitation": 0.0,
        "apparent_temperature": 3.0,  # repeated value, like dwd_weather: must be ignored
        "wind_speed": 10.0,
        "precipitation_probability": 10,
        "condition": "cloudy",
    }
    if 7 <= h < 11:
        item["temperature"] = [5.0, 6.0, 8.0, 9.0][h - 7]
        item["precipitation_probability"] = 20
    elif 11 <= h < 17:
        item.update(temperature=12.0 + (h - 11), wind_speed=35.0, wind_gust_speed=45.0)
        item.update(condition="rainy")
        item.update(precipitation=0.4, precipitation_probability=70 if h == 13 else 30)
    elif 17 <= h < 22:
        item["temperature"] = 12.0 - (h - 17)
    return item


@pytest.fixture
async def weather(hass: HomeAssistant):
    """Set up the mocked weather entity (UTC, so periods line up with the forecast)."""
    await hass.config.async_set_time_zone("UTC")
    forecast = [hour(h) for h in range(6, 24)]
    hass.states.async_set(
        WEATHER,
        "cloudy",
        {
            "friendly_name": "Home",
            "supported_features": WeatherEntityFeature.FORECAST_HOURLY,
            "temperature_unit": "°C",
            "wind_speed_unit": "km/h",
            "precipitation_unit": "mm",
        },
    )
    return async_mock_service(
        hass,
        "weather",
        "get_forecasts",
        response={WEATHER: {"forecast": forecast}},
        supports_response=SupportsResponse.ONLY,
    )


@pytest.fixture
def entry(hass: HomeAssistant, weather, freezer) -> MockConfigEntry:
    """A config entry with the default periods and rules."""
    freezer.move_to(NOW)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Layercast Home",
        unique_id=WEATHER,
        data={CONF_WEATHER_ENTITY: WEATHER},
        subentries_data=[
            {"data": data, "subentry_type": kind, "title": title, "unique_id": None}
            for kind, title, data in default_subentries("en")
        ],
    )
    entry.add_to_hass(hass)
    return entry
