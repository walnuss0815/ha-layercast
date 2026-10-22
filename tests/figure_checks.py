"""Checks for a figure folder, shared by the tests of the bundled figures and of the template."""

import json
import math
import re
from pathlib import Path

from custom_components.layercast.const import IMAGES

BASES = ["tshirt", "long_sleeve", "sweater"]
OUTER = ["jacket", "winter_coat", "rain_jacket"]
# Every layer worn under another must lie inside it.
PAIRS = [(b, o) for b in BASES for o in OUTER] + [
    ("jacket", "rain_jacket"),
    ("winter_coat", "rain_jacket"),
]


def load(folder: Path) -> dict:
    return json.loads((folder / "figure.json").read_text())


def assert_complete(folder: Path) -> None:
    """figure.json is valid and every file it names exists."""
    figure = load(folder)
    assert figure["width"] > 0 and figure["height"] > 0
    assert (folder / figure["base"]).is_file()
    for key, layer in figure["layers"].items():
        assert key in IMAGES, f"unknown image key {key}"
        assert (folder / layer["file"]).is_file(), f"{key}: {layer['file']} is missing"
        assert isinstance(layer["z"], int)


def silhouette(folder: Path, name: str) -> list[tuple[float, float]]:
    """The outline of a top: the points of its first path (an open jacket: its left half).

    Only the points of M and L segments count, so a figure that is drawn with polygons (like
    the neutral one) is checked exactly, one with curves roughly.
    """
    first_path = re.search(r'<path d="([^"]+)"', (folder / f"{name}.svg").read_text()).group(1)
    return [
        (float(x), float(y)) for x, y in re.findall(r"[ML]\s*(-?[\d.]+)\s+(-?[\d.]+)", first_path)
    ]


def inside(polygon, point) -> bool:
    x, y = point
    odd = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            odd = not odd
    return odd


def edge_distance(polygon, point) -> float:
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        dx, dy = x2 - x1, y2 - y1
        t = max(0, min(1, ((point[0] - x1) * dx + (point[1] - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(point[0] - x1 - t * dx, point[1] - y1 - t * dy))
    return best


def margin(under, over) -> float:
    """How far the outline `under` lies inside the outline `over` (negative: it sticks out).

    The neckline is left out (the first 2 units below the top of `under`): every top starts at the
    same neck, so there the outlines touch.
    """
    neck = min(y for _, y in under) + 2
    worst = float("inf")
    for (x1, y1), (x2, y2) in zip(under, under[1:] + under[:1], strict=True):
        for i in range(10):
            point = (x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
            if point[1] <= neck:
                continue
            distance = edge_distance(over, point)
            worst = min(worst, distance if inside(over, point) else -distance)
    return worst


def mirrored(polygon, width: float):
    return [(width - x, y) for x, y in polygon]


def has_layers(folder: Path, *names: str) -> bool:
    return all(name in load(folder)["layers"] for name in names)


def assert_tops_nest(folder: Path) -> None:
    """Every top lies inside the tops worn over it, the open light jacket inside the rain jacket."""
    for under, over in PAIRS:
        if has_layers(folder, under, over):
            m = margin(silhouette(folder, under), silhouette(folder, over))
            assert m >= 0.5, f"{under} sticks out of {over} ({m:.1f})"
    if has_layers(folder, "light_jacket", "rain_jacket"):
        half, rain = silhouette(folder, "light_jacket"), silhouette(folder, "rain_jacket")
        assert margin(half, rain) >= 0.5
        assert margin(mirrored(half, load(folder)["width"]), rain) >= 0.5
