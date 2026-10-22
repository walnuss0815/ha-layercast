"""Checks on the bundled figures and icons."""

import json
import os
from pathlib import Path

import pytest

from custom_components.layercast.const import IMAGES
from custom_components.layercast.defaults import RULES

from .figure_checks import (
    PAIRS,
    assert_complete,
    has_layers,
    load,
    margin,
    mirrored,
    silhouette,
)

WWW = Path(__file__).parents[1] / "custom_components" / "layercast" / "www"
FIGURES = sorted(p.parent for p in (WWW / "figures").glob("*/figure.json"))
# Figures that are not part of the repository can be checked too, with the same tests:
#   LAYERCAST_FIGURE_DIRS=/path/to/figure:/path/to/another pytest tests/test_figures.py
EXTRA_FIGURES = [Path(d) for d in os.environ.get("LAYERCAST_FIGURE_DIRS", "").split(":") if d]
ALL_FIGURES = FIGURES + EXTRA_FIGURES

# Items that cannot be worn: they are shown as a badge on every figure.
NOT_WORN = {"sunscreen", "generic"}


def test_there_is_a_neutral_figure():
    assert WWW / "figures" / "neutral" in FIGURES


@pytest.mark.parametrize("folder", ALL_FIGURES, ids=lambda p: p.name)
def test_figure_is_complete(folder: Path):
    assert_complete(folder)


def test_neutral_figure_draws_every_default_garment():
    figure = json.loads((WWW / "figures" / "neutral" / "figure.json").read_text())
    wanted = {image for _, image, _ in RULES} - NOT_WORN
    assert wanted <= set(figure["layers"])


def test_every_image_has_a_badge_icon():
    for image in IMAGES:
        assert (WWW / "icons" / f"{image}.svg").is_file(), image


# --- layers that are worn over each other must fit --------------------------------------

NEUTRAL = WWW / "figures" / "neutral"


def fit_cases():
    for folder in ALL_FIGURES:
        for under, over in PAIRS:
            yield pytest.param(folder, under, over, id=f"{folder.name}-{under}-{over}")


@pytest.mark.parametrize(("folder", "under", "over"), fit_cases())
def test_garments_fit_inside_the_ones_worn_over_them(folder: Path, under: str, over: str):
    if not has_layers(folder, under, over):
        pytest.skip(f"{folder.name} has no {under} or {over}")
    # An outline that pokes out would show the garment below as a sliver along the edge.
    assert margin(silhouette(folder, under), silhouette(folder, over)) >= 0.5


@pytest.mark.parametrize("folder", ALL_FIGURES, ids=lambda p: p.name)
def test_open_light_jacket_fits_inside_the_rain_jacket(folder: Path):
    if not has_layers(folder, "light_jacket", "rain_jacket"):
        pytest.skip(f"{folder.name} has no light_jacket or rain_jacket")
    half = silhouette(folder, "light_jacket")
    rain = silhouette(folder, "rain_jacket")
    assert margin(half, rain) >= 0.5
    assert margin(mirrored(half, load(folder)["width"]), rain) >= 0.5


def test_a_deliberately_small_jacket_is_detected():
    # The check itself: the t-shirt is not big enough to be worn over a jacket.
    assert margin(silhouette(NEUTRAL, "jacket"), silhouette(NEUTRAL, "tshirt")) < 0
