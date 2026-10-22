"""Tests for the pure rule engine."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from pytest import approx

from custom_components.layercast.rules import (
    aggregate,
    apparent_is_real,
    evaluate_period,
    feels_like,
    heat_index,
    match_rule,
    period_window,
    recommend,
    wind_chill,
)

TZ = ZoneInfo("Europe/Berlin")


def at(hour: int, day: int = 1) -> datetime:
    return datetime(2026, 10, day, hour, tzinfo=TZ)


def hours(start: int, temps: list[float], **extra) -> list[dict]:
    return [
        {"datetime": at(start) + timedelta(hours=i), "temperature": t, **extra}
        for i, t in enumerate(temps)
    ]


def test_window_before_during_after():
    start, end = time(7), time(11)
    assert period_window(at(5), start, end) == (at(7), at(11))
    assert period_window(at(9), start, end) == (at(7), at(11))
    assert period_window(at(12), start, end) == (at(7, 2), at(11, 2))


def test_window_overnight():
    start, end = time(22), time(6)
    assert period_window(at(23), start, end) == (at(22), at(6, 2))
    # Past midnight the occurrence that started yesterday is still running.
    assert period_window(at(2, 2), start, end) == (at(22), at(6, 2))
    assert period_window(at(12), start, end) == (at(22), at(6, 2))


def test_wind_chill_and_heat_index_reference_values():
    assert wind_chill(-10, 20) == approx(-17.9, abs=0.1)
    # NWS table: 90 F at 70 % humidity feels like about 106 F.
    assert heat_index((90 - 32) / 1.8, 70) == approx((106 - 32) / 1.8, abs=0.2)


def test_feels_like_cold_hot_mild_and_missing_inputs():
    cold = {"temperature": -10, "wind_speed": 20}
    assert feels_like(cold) == (approx(-17.9, abs=0.1), "computed")
    assert feels_like({"temperature": 5}) == (5, "temperature")  # no wind known
    assert feels_like({"temperature": 5, "wind_speed": 3}) == (5, "computed")  # calm
    assert feels_like({"temperature": 20}) == (20, "computed")
    assert feels_like({"temperature": 32}) == (32, "temperature")  # no humidity known
    hot = feels_like({"temperature": 32, "humidity": 70})
    assert hot[0] > 32 and hot[1] == "computed"
    assert feels_like({}) == (None, "temperature")


def test_constant_apparent_temperature_is_ignored():
    # Some sources (e.g. dwd_weather) repeat the current value for every hour.
    flat = hours(7, [5, 6, 7], apparent_temperature=3, wind_speed=20)
    assert not apparent_is_real(flat)
    agg = aggregate(flat, apparent_is_real(flat))
    assert agg["feels_like_source"] == "computed"
    assert agg["feels_min"] < 5

    real = hours(7, [5, 6, 7])
    for h, a in zip(real, [1, 2, 3], strict=True):
        h["apparent_temperature"] = a
    assert apparent_is_real(real)
    agg = aggregate(real, True)
    assert (agg["feels_min"], agg["feels_max"], agg["feels_like_source"]) == (1, 3, "forecast")


def test_aggregate_values():
    data = hours(
        7,
        [4, 9],
        precipitation=0.4,
        precipitation_probability=30,
        wind_speed=10,
        wind_gust_speed=25,
        condition="rainy",
    )
    data[1].update(precipitation=1.1, precipitation_probability=80, condition="cloudy")
    agg = aggregate(data, False)
    assert agg["temp_min"] == 4 and agg["temp_max"] == 9
    assert agg["rain_sum"] == 1.5 and agg["rain_probability_max"] == 80
    assert agg["wind_max"] == 10 and agg["gust_max"] == 25
    assert agg["conditions"] == ["cloudy", "rainy"]
    assert agg["uv_max"] is None  # not provided by the forecast


def test_match_rule_and_missing_data():
    agg = aggregate(hours(7, [4, 9], wind_speed=10), False)
    assert match_rule({"temp_below": 5}, agg) is True
    assert match_rule({"temp_below": 3}, agg) is False
    assert match_rule({"temp_above": 8, "wind": 10}, agg) is True  # AND, inclusive
    assert match_rule({"temp_above": 8, "wind": 11}, agg) is False
    assert match_rule({"uv": 3}, agg) is None  # forecast has no UV
    assert match_rule({"uv": 3, "temp_below": -50}, agg) is False  # fails whatever the UV is
    assert match_rule({"uv": 3, "temp_below": 50}, agg) is None  # could match, UV unknown
    assert match_rule({"conditions": ["sunny"]}, agg) is None  # no conditions known
    assert match_rule({}, agg) is True  # no conditions: always


def test_coldest_hour_must_reach_temp_min_above():
    agg = aggregate(hours(7, [16, 24]), False)
    assert match_rule({"temp_above": 22}, agg) is True  # warmest hour is enough
    assert match_rule({"temp_min_above": 22}, agg) is False  # coldest hour is not
    assert match_rule({"temp_min_above": 16}, agg) is True


def test_conditions_list_is_any_of():
    agg = aggregate(hours(7, [10], condition="rainy"), False)
    assert match_rule({"conditions": ["sunny", "rainy"]}, agg) is True
    assert match_rule({"conditions": ["sunny"]}, agg) is False


def test_unsupported_rules_are_only_reported_if_they_could_win():
    agg = aggregate(hours(7, [2]), False)  # no UV in the forecast
    rules = [
        {"name": "sun cap", "group": "head", "priority": 1, "uv": 6},
        {"name": "beanie", "group": "head", "priority": 2, "temp_below": 3},
        {"name": "helmet", "group": "head", "priority": 2, "uv": 6},  # same priority, listed later
        {"name": "visor", "group": "head", "priority": 3, "uv": 6},  # outranks the beanie
        {
            "name": "glasses",
            "group": "eyes",
            "priority": 1,
            "uv": 3,
        },  # nothing in the group matched
        {"name": "sunscreen", "uv": 6},  # no group: would be added
        {
            "name": "shades",
            "group": "eyes",
            "priority": 1,
            "uv": 3,
            "temp_above": 50,
        },  # cannot match
    ]
    items, unsupported = recommend(rules, agg)
    assert [r["name"] for r in items] == ["beanie"]
    assert [r["name"] for r in unsupported] == ["visor", "glasses", "sunscreen"]

    # a tie is won by the rule listed first
    rules = [
        {"name": "early", "group": "g", "uv": 6},
        {"name": "late", "group": "g", "temp_below": 3},
    ]
    items, unsupported = recommend(rules, agg)
    assert [r["name"] for r in items] == ["late"]
    assert [r["name"] for r in unsupported] == ["early"]


def test_groups_pick_highest_priority_and_ties_keep_first():
    agg = aggregate(hours(7, [2]), False)
    rules = [
        {"name": "light", "group": "outer", "priority": 1, "temp_below": 16},
        {"name": "coat", "group": " Outer ", "priority": 3, "temp_below": 5},
        {"name": "jacket", "group": "outer", "priority": 2, "temp_below": 10},
        {"name": "hat"},
        {"name": "sunscreen", "uv": 6},
        {"name": "tie-a", "group": "x", "priority": 1},
        {"name": "tie-b", "group": "x", "priority": 1},
    ]
    items, unsupported = recommend(rules, agg)
    assert [r["name"] for r in items] == ["coat", "hat", "tie-a"]
    assert [r["name"] for r in unsupported] == ["sunscreen"]  # no group: it would be added


def test_evaluate_period_end_to_end():
    forecast = hours(0, [3] * 24, wind_speed=15)
    forecast[8]["temperature"] = 12  # morning warms up
    period = {"start": "07:00:00", "end": "11:00:00"}
    rules = [{"name": "jacket", "temp_below": 5}, {"name": "shorts", "temp_above": 25}]

    result = evaluate_period(forecast, period, rules, at(6))
    assert (result["start"], result["end"], result["hours"]) == (at(7), at(11), 4)
    assert result["values"]["temp_max"] == 12
    assert [r["name"] for r in result["items"]] == ["jacket"]

    # Already over today: the same period tomorrow has no forecast yet.
    tomorrow = evaluate_period(forecast, period, rules, at(12))
    assert tomorrow["start"] == at(7, 2) and tomorrow["hours"] == 0
    assert tomorrow["items"] == [] and tomorrow["values"] == {}
