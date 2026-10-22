"""Default periods and rules created with a new entry. All of them are editable."""

from .const import SUBENTRY_PERIOD, SUBENTRY_RULE

PERIODS = [
    ("morning", "07:00:00", "11:00:00"),
    ("day", "11:00:00", "17:00:00"),
    ("evening", "17:00:00", "22:00:00"),
]

# key, image, group/priority/conditions. Within a group the matching rule with the
# highest priority wins. Outerwear, hats and gloves use feels-like (wind matters),
# the base layer and legs the actual temperature. Rain uses the amount, not the probability:
# some sources (dwd_weather with hourly updates) have none. 0.5 mm is DWD's threshold for rain;
# gusts of 39 km/h (Beaufort 6) are where umbrellas become hard to use.
RULES = [
    ("t_shirt", "tshirt", {"group": "base", "priority": 1}),
    ("long_sleeve", "long_sleeve", {"group": "base", "priority": 2, "temp_below": 18}),
    ("sweater", "sweater", {"group": "base", "priority": 3, "temp_below": 10}),
    ("light_jacket", "light_jacket", {"group": "outer", "priority": 1, "feels_below": 16}),
    ("jacket", "jacket", {"group": "outer", "priority": 2, "feels_below": 10}),
    ("winter_coat", "winter_coat", {"group": "outer", "priority": 3, "feels_below": 0}),
    (
        "rain_jacket",
        "rain_jacket",
        {"group": "rain", "priority": 2, "rain_amount": 0.5, "gusts": 39},
    ),
    ("umbrella", "umbrella", {"group": "rain", "priority": 1, "rain_amount": 0.5}),
    ("trousers", "trousers", {"group": "legs", "priority": 1}),
    ("shorts", "shorts", {"group": "legs", "priority": 2, "temp_min_above": 18}),
    ("thermal_trousers", "thermal_trousers", {"group": "legs", "priority": 3, "feels_below": -5}),
    ("sneakers", "sneakers", {"group": "shoes", "priority": 1}),
    ("boots", "boots", {"group": "shoes", "priority": 2, "feels_below": 3}),
    ("rain_boots", "rain_boots", {"group": "shoes", "priority": 3, "rain_amount": 2}),
    ("sun_cap", "sun_cap", {"group": "head", "priority": 1, "uv": 6}),
    ("hat", "hat", {"group": "head", "priority": 2, "feels_below": 3}),
    ("gloves", "gloves", {"feels_below": 3}),
    ("sunglasses", "sunglasses", {"group": "eyes", "priority": 1, "conditions": ["sunny"]}),
    ("sunglasses_uv", "sunglasses", {"group": "eyes", "priority": 1, "uv": 3}),
    ("sunscreen", "sunscreen", {"uv": 6}),
]

NAMES = {
    "en": {
        "morning": "Morning",
        "day": "Day",
        "evening": "Evening",
        "t_shirt": "T-shirt",
        "long_sleeve": "Long sleeve",
        "sweater": "Sweater",
        "light_jacket": "Light jacket",
        "jacket": "Jacket",
        "winter_coat": "Winter coat",
        "rain_jacket": "Rain jacket",
        "umbrella": "Umbrella",
        "trousers": "Trousers",
        "shorts": "Shorts",
        "thermal_trousers": "Thermal trousers",
        "sneakers": "Sneakers",
        "boots": "Boots",
        "rain_boots": "Rain boots",
        "sun_cap": "Sun cap",
        "hat": "Hat",
        "gloves": "Gloves",
        "sunglasses": "Sunglasses",
        "sunglasses_uv": "Sunglasses (UV)",
        "sunscreen": "Sunscreen",
    },
    "de": {
        "morning": "Morgen",
        "day": "Tag",
        "evening": "Abend",
        "t_shirt": "T-Shirt",
        "long_sleeve": "Langarmshirt",
        "sweater": "Pullover",
        "light_jacket": "Leichte Jacke",
        "jacket": "Jacke",
        "winter_coat": "Winterjacke",
        "rain_jacket": "Regenjacke",
        "umbrella": "Regenschirm",
        "trousers": "Hose",
        "shorts": "Kurze Hose",
        "thermal_trousers": "Thermohose",
        "sneakers": "Turnschuhe",
        "boots": "Stiefel",
        "rain_boots": "Gummistiefel",
        "sun_cap": "Sonnenkappe",
        "hat": "Mütze",
        "gloves": "Handschuhe",
        "sunglasses": "Sonnenbrille",
        "sunglasses_uv": "Sonnenbrille (UV)",
        "sunscreen": "Sonnencreme",
    },
}


def default_subentries(language: str) -> list[tuple[str, str, dict]]:
    """Return (subentry type, title, data) for the default periods and rules."""
    names = NAMES["de" if language.startswith("de") else "en"]
    periods = [
        (SUBENTRY_PERIOD, names[key], {"name": names[key], "start": start, "end": end})
        for key, start, end in PERIODS
    ]
    rules = [
        (SUBENTRY_RULE, names[key], {"name": names[key], "image": image, **conditions})
        for key, image, conditions in RULES
    ]
    return periods + rules
