"""The figure template of the figure-generator skill must keep producing a valid figure."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from custom_components.layercast.const import IMAGES

from .figure_checks import assert_complete, assert_tops_nest, load

SKILL = Path(__file__).parents[1] / ".opencode" / "skills" / "figure-generator"
TEMPLATE = SKILL / "template" / "generate_figure.py"


@pytest.fixture(scope="module")
def figure(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("figure")
    # The script itself checks that the tops nest, and exits with 1 if not.
    result = subprocess.run(
        [sys.executable, str(TEMPLATE), "--out", str(out), "--name", "Test"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return out


def test_the_template_writes_a_complete_figure(figure: Path):
    assert_complete(figure)
    layers = load(figure)["layers"]
    assert load(figure)["name"] == "Test"
    # every garment a rule can recommend, except the ones that cannot be worn
    assert set(layers) == set(IMAGES) - {"sunscreen", "generic"}


def test_the_tops_of_the_template_nest(figure: Path):
    assert_tops_nest(figure)


def test_every_layer_is_valid_svg_on_the_canvas(figure: Path):
    data = load(figure)
    for path in figure.glob("*.svg"):
        text = path.read_text()
        assert text.startswith("<svg"), path.name
        assert f'viewBox="0 0 {data["width"]} {data["height"]}"' in text, path.name
        assert text.count("<") == text.count(">"), path.name
    assert (figure / "figure.json").read_text().endswith("\n")


def test_the_check_of_the_template_notices_a_jacket_that_is_too_small(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location("template_under_test", TEMPLATE)
    template = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(template)
    # a rain jacket as small as a t-shirt cannot be worn over a jacket
    template.TOPS["rain_jacket"] = dict(template.TOPS["tshirt"])
    assert template.main(["--out", str(tmp_path)]) == 1
    assert "too small" in capsys.readouterr().err


def test_the_skill_files_exist_and_are_described():
    text = (SKILL / "SKILL.md").read_text()
    assert text.startswith("---\nname: figure-generator\ndescription: ")
    assert (SKILL / "template" / "measure_reference.py").is_file()
    # the skill points at files that exist, instead of copying their content
    for referenced in (
        "custom_components/layercast/const.py",
        "custom_components/layercast/www/figures/neutral/figure.json",
        "tests/test_figures.py",
        "docs/screenshot/figures.mjs",
    ):
        assert referenced in text
        assert (SKILL.parents[2] / referenced).exists(), referenced
    json.dumps(text)  # plain text


def test_the_side_by_side_tool_puts_two_pictures_at_the_same_height(tmp_path):
    from PIL import Image

    Image.new("RGB", (100, 300), "#000000").save(tmp_path / "reference.png")
    Image.new("RGB", (200, 400), "#ffffff").save(tmp_path / "render.png")
    out = tmp_path / "compare.png"
    tool = SKILL / "template" / "side_by_side.py"
    result = subprocess.run(
        [
            sys.executable,
            str(tool),
            str(tmp_path / "reference.png"),
            str(tmp_path / "render.png"),
            "--out",
            str(out),
            "--height",
            "300",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    sheet = Image.open(out)
    assert sheet.height == 300
    # the reference keeps its proportions (100 x 300); the render is cropped to 92 % of its height
    assert sheet.width == 100 + 30 + round(200 * 300 / (400 * 0.92))


def test_the_measure_tool_finds_a_figure_on_a_plain_background(tmp_path):
    from PIL import Image, ImageDraw

    picture = Image.new("RGB", (100, 200), "#101010")
    draw = ImageDraw.Draw(picture)
    draw.rectangle((40, 20, 60, 180), fill="#ffd90f")  # a bar: 21 px wide, 161 px tall
    picture.save(tmp_path / "ref.png")
    tool = SKILL / "template" / "measure_reference.py"
    result = subprocess.run(
        [sys.executable, str(tool), str(tmp_path / "ref.png"), "--rows", "4"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "height 161px" in result.stdout
    # a bar of 21 px (+/- 10 around the middle) on a figure 161 px tall: +/- 6.2 percent of it
    rows = [line for line in result.stdout.splitlines() if "-6.2..  6.2" in line]
    assert len(rows) == 4
    assert all(line.rstrip().endswith("#f0d010") for line in rows)
