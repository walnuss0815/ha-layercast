"""Measures the proportions of a reference picture of a figure (needs Pillow).

    python measure_reference.py picture.png [--rows 40] [--tolerance 60] [--background #rrggbb]

The picture is only measured, never traced or copied: use the numbers to set the PARAMETERS of
generate_figure.py. It should show the whole figure from the front, standing, on a plain
background (a transparent one works too).

Output, for the rows from the top of the figure to its feet:
  y      the height as a percentage of the figure's height (0 = top of the head)
  runs   the horizontal runs of figure, as x ranges in percent of the figure's height, measured from
         the middle of the figure (negative = left). Two runs in one row mean a gap, for example
         between an arm and the body, or between the legs.
  colour the most common colour in the row

To get canvas numbers: y_canvas = TOP + y% * HEIGHT and x_canvas = CX + x% * HEIGHT, where HEIGHT is
the height the figure should have on the canvas (for example 280 of 320, leaving room for the
umbrella and the hat) and TOP the canvas y of its top.
"""

import argparse
import sys
from collections import Counter

from PIL import Image


def parse_color(text: str):
    text = text.lstrip("#")
    return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))


def background_of(image: Image.Image):
    """The most common colour of the four corners."""
    w, h = image.size
    corners = [image.getpixel(p)[:3] for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    return Counter(corners).most_common(1)[0][0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("picture")
    parser.add_argument("--rows", type=int, default=40, help="how many rows to print")
    parser.add_argument(
        "--tolerance", type=int, default=60, help="colour distance to the background"
    )
    parser.add_argument("--background", help="background colour, default: the corners")
    args = parser.parse_args(argv)

    image = Image.open(args.picture).convert("RGBA")
    w, h = image.size
    background = parse_color(args.background) if args.background else background_of(image)

    def is_figure(p) -> bool:
        if p[3] < 40:
            return False
        return sum(abs(a - b) for a, b in zip(p[:3], background, strict=True)) > args.tolerance

    mask = [[is_figure(image.getpixel((x, y))) for x in range(w)] for y in range(h)]
    rows = [y for y in range(h) if any(mask[y])]
    if not rows:
        print("no figure found: try --background or a smaller --tolerance", file=sys.stderr)
        return 1
    top, bottom = rows[0], rows[-1]
    height = bottom - top + 1
    columns = [x for x in range(w) if any(mask[y][x] for y in range(top, bottom + 1))]
    centre = (columns[0] + columns[-1]) / 2
    print(f"picture {w}x{h}px, background rgb{background}")
    print(f"figure: top {top}, bottom {bottom}, height {height}px, middle x {centre:.1f}")
    print(f"{'y %':>6}  {'runs (x in % of height, from the middle)':<50} colour")

    for i in range(args.rows):
        y = top + int((i + 0.5) * height / args.rows)
        runs, start = [], None
        for x in range(w + 1):
            on = x < w and mask[y][x]
            if on and start is None:
                start = x
            if not on and start is not None:
                if x - start >= max(2, w // 200):  # ignore specks
                    runs.append((start, x - 1))
                start = None
        text = "  ".join(
            f"{(a - centre) * 100 / height:6.1f}..{(b - centre) * 100 / height:5.1f}"
            for a, b in runs
        )
        colors = Counter(
            tuple(v // 32 * 32 + 16 for v in image.getpixel((x, y))[:3])
            for a, b in runs
            for x in range(a, b + 1)
        )
        common = colors.most_common(1)[0][0] if colors else (0, 0, 0)
        hex_ = f"#{common[0]:02x}{common[1]:02x}{common[2]:02x}"
        print(f"{(y - top) * 100 / height:6.1f}  {text:<50} {hex_}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
