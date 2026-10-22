"""Constants for Layercast."""

from datetime import timedelta

DOMAIN = "layercast"

CONF_WEATHER_ENTITY = "weather_entity"

SUBENTRY_PERIOD = "period"
SUBENTRY_RULE = "rule"

UPDATE_INTERVAL = timedelta(minutes=15)

# UV is only counted while the sun is above this elevation (degrees). Some sources,
# like dwd_weather, repeat the daily UV maximum for every hour of the day.
# ponytail: rough threshold, make it an option if someone needs to tune it.
MIN_UV_SUN_ELEVATION = 10

STATIC_URL = "/layercast_static"
CARD_URL = f"{STATIC_URL}/layercast-card.js"

# Image keys of a rule. Each has a badge icon in www/icons/<key>.svg; a figure
# (www/figures/<figure>/figure.json) draws the ones it has a layer for.
IMAGES = [
    "tshirt",
    "long_sleeve",
    "sweater",
    "light_jacket",
    "jacket",
    "winter_coat",
    "rain_jacket",
    "umbrella",
    "hat",
    "sun_cap",
    "gloves",
    "sunglasses",
    "sunscreen",
    "trousers",
    "shorts",
    "thermal_trousers",
    "sneakers",
    "boots",
    "rain_boots",
    "generic",
]

WEATHER_CONDITIONS = [
    "clear-night",
    "cloudy",
    "exceptional",
    "fog",
    "hail",
    "lightning",
    "lightning-rainy",
    "partlycloudy",
    "pouring",
    "rainy",
    "snowy",
    "snowy-rainy",
    "sunny",
    "windy",
    "windy-variant",
]
