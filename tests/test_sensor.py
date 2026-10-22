"""Setup, unload and sensor tests."""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.layercast.const import CARD_URL

from .conftest import WEATHER, hour


async def test_setup_unload_and_card(hass: HomeAssistant, entry: MockConfigEntry, add_extra_js_url):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.async_entity_ids("sensor") == [
        "sensor.layercast_home_morning",
        "sensor.layercast_home_day",
        "sensor.layercast_home_evening",
    ]
    # The card is served and registered for the frontend.
    add_extra_js_url.assert_called_once()
    assert add_extra_js_url.call_args.args[1].startswith(f"{CARD_URL}?v=")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.layercast_home_morning").state == STATE_UNAVAILABLE


async def test_recommendations(hass: HomeAssistant, entry: MockConfigEntry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    morning = hass.states.get("sensor.layercast_home_morning")
    # Cold, and wind chill applies: the actual temperature would not give a hat and gloves.
    assert morning.state == "Sweater, Jacket, Trousers, Boots, Hat, Gloves"
    # No UV in the forecast: UV rules are reported, not guessed. The sun cap is left out: the hat
    # that matched outranks it in the same group, so it could not change anything.
    assert morning.attributes["unsupported"] == ["Sunglasses (UV)", "Sunscreen"]
    assert morning.attributes["period"] == "Morning"
    assert morning.attributes["hours"] == 4
    assert morning.attributes["start"] == "2026-10-22T07:00:00+00:00"
    assert morning.attributes["values"]["temp_min"] == 5.0
    assert morning.attributes["values"]["feels_like_source"] == "computed"
    assert morning.attributes["items"][0] == {"name": "Sweater", "image": "sweater"}

    # The rain jacket (rain and wind) wins over the umbrella in the same group.
    day = hass.states.get("sensor.layercast_home_day")
    assert day.state == "Long sleeve, Light jacket, Rain jacket, Trousers, Rain boots"

    evening = hass.states.get("sensor.layercast_home_evening")
    assert evening.state == "Sweater, Jacket, Trousers, Sneakers"


async def test_uv_only_counts_while_the_sun_is_up(hass: HomeAssistant, entry: MockConfigEntry):
    # Like dwd_weather: the daily UV maximum is repeated for every hour of the day.
    forecast = [{**hour(h), "uv_index": 8} for h in range(6, 24)]
    async_mock_service(
        hass,
        "weather",
        "get_forecasts",
        response={WEATHER: {"forecast": forecast}},
        supports_response=SupportsResponse.ONLY,
    )
    # On the equator at longitude 0 the sun is high at 07-17 UTC and low from 17:00.
    hass.config.latitude = 0
    hass.config.longitude = 0
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    day = hass.states.get("sensor.layercast_home_day")
    assert day.attributes["values"]["uv_max"] == 8
    assert "Sun cap" in day.state and "Sunscreen" in day.state
    assert day.attributes["unsupported"] == []

    evening = hass.states.get("sensor.layercast_home_evening")
    assert evening.attributes["values"]["uv_max"] == 0
    assert "Sun cap" not in evening.state and "Sunscreen" not in evening.state
    assert evening.attributes["unsupported"] == []  # known to be 0, not missing


async def test_period_over_today_rolls_to_tomorrow(
    hass: HomeAssistant, entry: MockConfigEntry, freezer
):
    freezer.move_to("2026-10-22T12:00:00+00:00")
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    morning = hass.states.get("sensor.layercast_home_morning")
    assert morning.attributes["start"] == "2026-10-23T07:00:00+00:00"
    assert morning.state == "unknown"  # no forecast that far yet


async def test_weather_unavailable_retries_setup(hass: HomeAssistant, entry: MockConfigEntry):
    hass.states.async_set(WEATHER, STATE_UNAVAILABLE)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_card_and_figures_are_served(
    hass: HomeAssistant, entry: MockConfigEntry, hass_client
):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()

    card = await client.get(CARD_URL)
    assert card.status == 200
    assert "layercast-card" in await card.text()

    figure = await client.get("/layercast_static/figures/neutral/figure.json")
    assert figure.status == 200
    assert (await figure.json())["layers"]["jacket"]["file"] == "jacket.svg"

    icon = await client.get("/layercast_static/icons/sunscreen.svg")
    assert icon.status == 200


async def test_all_period_sensors_share_one_device(
    hass: HomeAssistant, entry: MockConfigEntry, caplog
):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entities) == 3
    assert len({e.device_id for e in entities}) == 1

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [(d.name, d.entry_type) for d in devices] == [
        ("Layercast Home", dr.DeviceEntryType.SERVICE)
    ]
    # Moving a device between subentries is deprecated and would log this.
    assert "silently moves" not in caplog.text


async def test_deleting_a_period_removes_its_sensor(hass: HomeAssistant, entry: MockConfigEntry):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.layercast_home_evening") is not None

    evening = next(s for s in entry.get_subentries_of_type("period") if s.title == "Evening")
    hass.config_entries.async_remove_subentry(entry, evening.subentry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.layercast_home_evening") is None
    assert hass.states.get("sensor.layercast_home_morning") is not None  # others stay
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1  # the shared device stays


async def test_rain_rules_work_without_rain_probability(
    hass: HomeAssistant, entry: MockConfigEntry
):
    # dwd_weather with hourly updates has rain amounts, but no probability.
    forecast = [{**hour(h), "precipitation_probability": None} for h in range(6, 24)]
    async_mock_service(
        hass,
        "weather",
        "get_forecasts",
        response={WEATHER: {"forecast": forecast}},
        supports_response=SupportsResponse.ONLY,
    )
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    day = hass.states.get("sensor.layercast_home_day")
    assert "Rain jacket" in day.state and "Rain boots" in day.state
    assert day.attributes["unsupported"] == ["Sun cap", "Sunglasses (UV)", "Sunscreen"]

    evening = hass.states.get("sensor.layercast_home_evening")  # dry
    assert "Rain jacket" not in evening.state and "Umbrella" not in evening.state
    assert not {"Umbrella", "Rain jacket"} & set(evening.attributes["unsupported"])
