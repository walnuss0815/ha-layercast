"""Pure rule engine: period windows, aggregation, feels-like and rule matching.

No Home Assistant imports. Forecast hours are dicts in canonical units
(degC, km/h, mm) with a timezone-aware ``datetime``, using the keys of
the Home Assistant weather forecast (``temperature``, ``humidity``, ...).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from operator import ge, le
from typing import Any

# Rule condition key -> (aggregate key, comparison). "below" conditions look
# at the coldest hour of the period, "above" ones at the warmest, and
# "min_above" ones need even the coldest hour to reach the value.
CONDITIONS: dict[str, tuple[str, Any]] = {
    "temp_below": ("temp_min", le),
    "temp_above": ("temp_max", ge),
    "temp_min_above": ("temp_min", ge),
    "feels_below": ("feels_min", le),
    "feels_above": ("feels_max", ge),
    "rain_probability": ("rain_probability_max", ge),
    "rain_amount": ("rain_sum", ge),
    "wind": ("wind_max", ge),
    "gusts": ("gust_max", ge),
    "uv": ("uv_max", ge),
    "humidity": ("humidity_max", ge),
}


def period_window(now: datetime, start: time, end: time) -> tuple[datetime, datetime]:
    """Return the current or next occurrence of a period.

    A period that already ended rolls over to tomorrow; ``end <= start``
    means the period runs past midnight.
    """

    def window(offset: int) -> tuple[datetime, datetime]:
        day = now.date() + timedelta(days=offset)
        end_day = day if end > start else day + timedelta(days=1)
        return (
            datetime.combine(day, start, now.tzinfo),
            datetime.combine(end_day, end, now.tzinfo),
        )

    # Yesterday's occurrence matters for overnight periods still running.
    return next(w for w in map(window, (-1, 0, 1)) if w[1] > now)


def heat_index(temp_c: float, humidity: float) -> float:
    """Heat index (NWS Rothfusz regression) in degC."""
    t = temp_c * 1.8 + 32
    r = humidity
    hi = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * r
        - 0.22475541 * t * r
        - 0.00683783 * t * t
        - 0.05481717 * r * r
        + 0.00122874 * t * t * r
        + 0.00085282 * t * r * r
        - 0.00000199 * t * t * r * r
    )
    return (hi - 32) / 1.8


def wind_chill(temp_c: float, wind_kmh: float) -> float:
    """Wind chill (Environment Canada / NWS) in degC; valid <= 10 degC, > 4.8 km/h."""
    v = wind_kmh**0.16
    return 13.12 + 0.6215 * temp_c - 11.37 * v + 0.3965 * temp_c * v


def feels_like(hour: dict) -> tuple[float | None, str]:
    """Calculate feels-like for one hour as (value, source).

    ``source`` is "computed", or "temperature" when the formula needed an
    input the forecast lacks and the plain temperature was used instead.
    """
    temp = hour.get("temperature")
    if temp is None:
        return None, "temperature"
    wind = hour.get("wind_speed")
    humidity = hour.get("humidity")
    if temp <= 10:
        if wind is None:
            return temp, "temperature"
        if wind > 4.8:
            return wind_chill(temp, wind), "computed"
    elif temp >= 27:
        if humidity is None:
            return temp, "temperature"
        return max(temp, heat_index(temp, humidity)), "computed"
    return temp, "computed"


def apparent_is_real(hours: list[dict]) -> bool:
    """Whether the source's apparent_temperature is a real per-hour forecast.

    Some sources repeat one current value for every hour; that is useless.
    """
    return (
        len({h["apparent_temperature"] for h in hours if h.get("apparent_temperature") is not None})
        > 1
    )


def aggregate(hours: list[dict], use_apparent: bool) -> dict[str, Any]:
    """Reduce the hours of a period to the values rules are matched against."""

    def values(key: str) -> list[float]:
        return [h[key] for h in hours if h.get(key) is not None]

    def hi(items: list[float]) -> float | None:
        return round(max(items), 1) if items else None

    def lo(items: list[float]) -> float | None:
        return round(min(items), 1) if items else None

    feels: list[float] = []
    sources: list[str] = []
    for h in hours:
        apparent = h.get("apparent_temperature")
        value, source = (
            (apparent, "forecast") if use_apparent and apparent is not None else feels_like(h)
        )
        if value is not None:
            feels.append(value)
            sources.append(source)

    temps = values("temperature")
    rain = values("precipitation")
    if not sources:
        feels_source = None
    elif set(sources) == {"forecast"}:
        feels_source = "forecast"
    elif "temperature" in sources:
        feels_source = "temperature"
    else:
        feels_source = "computed"

    return {
        "temp_min": lo(temps),
        "temp_max": hi(temps),
        "feels_min": lo(feels),
        "feels_max": hi(feels),
        "feels_like_source": feels_source,
        "rain_probability_max": hi(values("precipitation_probability")),
        "rain_sum": round(sum(rain), 1) if rain else None,
        "wind_max": hi(values("wind_speed")),
        "gust_max": hi(values("wind_gust_speed")),
        "uv_max": hi(values("uv_index")),
        "humidity_max": hi(values("humidity")),
        "conditions": sorted(set(values("condition"))),
    }


def match_rule(rule: dict, agg: dict) -> bool | None:
    """True if the rule matches, False if not, None if the forecast lacks data it needs.

    A condition that fails settles it, even if another one cannot be evaluated: the
    rule would not match whatever the missing value is.
    """
    results: list[bool] = []
    unknown = False
    for key, (agg_key, compare) in CONDITIONS.items():
        limit = rule.get(key)
        if limit is None:
            continue
        value = agg[agg_key]
        if value is None:
            unknown = True
        else:
            results.append(compare(value, limit))
    wanted = rule.get("conditions")
    if wanted:
        if agg["conditions"]:
            results.append(bool(set(wanted) & set(agg["conditions"])))
        else:
            unknown = True
    if not all(results):
        return False
    return None if unknown else True


def recommend(rules: list[dict], agg: dict) -> tuple[list[dict], list[dict]]:
    """Return (matching rules, unsupported rules that could change the recommendation).

    Within a group only the highest-priority match is kept; on a tie the
    rule listed first wins. Rules without a group always show. An unsupported
    rule is only reported if it could win: a rule that a matched rule of
    its group outranks would not change anything, so it is left out.
    """
    matched: list[tuple[int, dict]] = []
    unsupported: list[tuple[int, dict]] = []
    for index, rule in enumerate(rules):
        result = match_rule(rule, agg)
        if result is None:
            unsupported.append((index, rule))
        elif result:
            matched.append((index, rule))

    def group(rule: dict) -> str:
        return (rule.get("group") or "").strip().casefold()

    def priority(rule: dict) -> int:
        return rule.get("priority", 0)

    best: dict[str, tuple[int, dict]] = {}
    for index, rule in matched:
        g = group(rule)
        if g and (g not in best or priority(rule) > priority(best[g][1])):
            best[g] = (index, rule)
    items = [r for _, r in matched if not group(r) or best[group(r)][1] is r]

    def could_win(index: int, rule: dict) -> bool:
        g = group(rule)
        if not g or g not in best:
            return True
        best_index, winner = best[g]
        return priority(rule) > priority(winner) or (
            priority(rule) == priority(winner) and index < best_index
        )

    return items, [r for i, r in unsupported if could_win(i, r)]


def evaluate_period(forecast: list[dict], period: dict, rules: list[dict], now: datetime) -> dict:
    """Evaluate one period against an hourly forecast."""
    start, end = period_window(
        now, time.fromisoformat(period["start"]), time.fromisoformat(period["end"])
    )
    hours = [h for h in forecast if start <= h["datetime"] < end]
    result: dict[str, Any] = {
        "start": start,
        "end": end,
        "hours": len(hours),
        "values": {},
        "items": [],
        "unsupported": [],
    }
    if hours:
        agg = aggregate(hours, apparent_is_real(forecast))
        result["values"] = agg
        result["items"], result["unsupported"] = recommend(rules, agg)
    return result
