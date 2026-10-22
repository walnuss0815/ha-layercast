"""Tests for forecast normalisation and rule items."""

from datetime import datetime

from pytest import approx

from custom_components.layercast.coordinator import normalize_forecast, rule_item


def test_normalize_converts_units_and_keeps_none():
    forecast = [
        {
            "datetime": "2026-10-22T07:00:00+00:00",
            "temperature": 50,
            "wind_speed": 10,
            "precipitation": 1,
            "humidity": 80,
            "condition": "rainy",
        },
        {"datetime": "not a date"},
    ]
    attributes = {"temperature_unit": "°F", "wind_speed_unit": "mph", "precipitation_unit": "in"}
    (hour,) = normalize_forecast(forecast, attributes)
    assert hour["temperature"] == approx(10)
    assert hour["wind_speed"] == approx(16.09, abs=0.01)
    assert hour["precipitation"] == approx(25.4)
    assert hour["humidity"] == 80 and hour["condition"] == "rainy"
    assert hour["wind_gust_speed"] is None
    assert hour["uv_index"] is None


def test_uv_of_hours_with_a_low_sun_is_zero():
    forecast = [
        {"datetime": "2026-10-22T12:00:00+00:00", "uv_index": 6},
        {"datetime": "2026-10-22T19:00:00+00:00", "uv_index": 6},  # repeated daily maximum
        {"datetime": "2026-10-22T19:00:00+00:00"},  # the source has no UV at all
    ]

    def elevation(when: datetime) -> float:
        return 50 if when.hour < 15 else 3  # the middle of the hour is passed in

    noon, evening, unknown = normalize_forecast(forecast, {}, elevation)
    assert noon["uv_index"] == 6
    assert evening["uv_index"] == 0
    assert unknown["uv_index"] is None  # stays missing, so UV rules stay unsupported

    (untouched,) = normalize_forecast(forecast[1:2], {})  # no elevation given
    assert untouched["uv_index"] == 6


def test_elevation_is_checked_in_the_middle_of_the_hour():
    seen = []
    normalize_forecast(
        [{"datetime": "2026-10-22T19:00:00+00:00", "uv_index": 1}],
        {},
        lambda when: seen.append(when) or 90,
    )
    assert seen[0].isoformat() == "2026-10-22T19:30:00+00:00"


def test_rule_item():
    assert rule_item({"name": "Jacket", "image": "jacket"}) == {"name": "Jacket", "image": "jacket"}
    assert rule_item({"name": "Own"}) == {"name": "Own", "image": "generic"}
    assert rule_item({"name": "Own", "image": "jacket", "image_url": "/local/j.png"}) == {
        "name": "Own",
        "image": "jacket",
        "image_url": "/local/j.png",
    }
