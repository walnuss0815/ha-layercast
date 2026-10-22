"""Config and subentry flow tests."""

from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.layercast.const import (
    CONF_WEATHER_ENTITY,
    DOMAIN,
    SUBENTRY_PERIOD,
    SUBENTRY_RULE,
)

from .conftest import WEATHER


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _subentry(entry: MockConfigEntry, kind: str, title: str):
    return next(s for s in entry.get_subentries_of_type(kind) if s.title == title)


async def test_user_flow_creates_defaults(hass: HomeAssistant, weather):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEATHER_ENTITY: WEATHER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.title == "Layercast Home"
    assert entry.unique_id == WEATHER
    assert [s.title for s in entry.get_subentries_of_type(SUBENTRY_PERIOD)] == [
        "Morning",
        "Day",
        "Evening",
    ]
    assert len(entry.get_subentries_of_type(SUBENTRY_RULE)) == 20


async def test_defaults_follow_language(hass: HomeAssistant, weather):
    hass.config.language = "de"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEATHER_ENTITY: WEATHER}
    )
    titles = [s.title for s in result["result"].get_subentries_of_type(SUBENTRY_PERIOD)]
    assert titles == ["Morgen", "Tag", "Abend"]


async def test_user_flow_requires_hourly_forecast(hass: HomeAssistant, weather):
    hass.states.async_set("weather.daily_only", "sunny", {"supported_features": 0})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEATHER_ENTITY: "weather.daily_only"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_WEATHER_ENTITY: "no_hourly_forecast"}


async def test_user_flow_already_configured(hass: HomeAssistant, entry: MockConfigEntry):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEATHER_ENTITY: WEATHER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_weather_entity(hass: HomeAssistant, entry: MockConfigEntry):
    hass.states.async_set(
        "weather.office", "sunny", {"supported_features": WeatherEntityFeature.FORECAST_HOURLY}
    )
    await _setup(hass, entry)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_WEATHER_ENTITY: "weather.office"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_WEATHER_ENTITY] == "weather.office"
    assert entry.unique_id == "weather.office"
    assert len(entry.get_subentries_of_type(SUBENTRY_RULE)) == 20  # rules are kept


async def test_add_and_reconfigure_period(hass: HomeAssistant, entry: MockConfigEntry):
    await _setup(hass, entry)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERIOD), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Night", "start": "22:00:00", "end": "06:00:00"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("sensor.layercast_home_night") is not None  # entry was reloaded

    night = _subentry(entry, SUBENTRY_PERIOD, "Night")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_PERIOD),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": night.subentry_id},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Late", "start": "21:00:00", "end": "05:00:00"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert night.title == "Late" and night.data["start"] == "21:00:00"


async def test_add_rule_in_two_steps(hass: HomeAssistant, entry: MockConfigEntry):
    await _setup(hass, entry)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_RULE), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"name": "Snow gaiters"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "conditions"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"temp_below": 0, "temp_min_above": -10, "conditions": ["snowy"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    gaiters = _subentry(entry, SUBENTRY_RULE, "Snow gaiters")
    assert dict(gaiters.data) == {
        "name": "Snow gaiters",
        "image": "generic",
        "priority": 0,
        "temp_below": 0,
        "temp_min_above": -10,
        "conditions": ["snowy"],
    }


async def test_reconfigure_rule_replaces_conditions(hass: HomeAssistant, entry: MockConfigEntry):
    await _setup(hass, entry)
    jacket = _subentry(entry, SUBENTRY_RULE, "Jacket")
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_RULE),
        context={"source": SOURCE_RECONFIGURE, "subentry_id": jacket.subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Warm jacket", "image": "jacket", "group": "outer", "priority": 4},
    )
    assert result["step_id"] == "conditions"
    # Clearing a field removes the condition instead of keeping the old value.
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"rain_probability": 40}
    )
    assert result["type"] is FlowResultType.ABORT
    assert jacket.title == "Warm jacket"
    assert dict(jacket.data) == {
        "name": "Warm jacket",
        "image": "jacket",
        "group": "outer",
        "priority": 4,
        "rain_probability": 40,
    }
