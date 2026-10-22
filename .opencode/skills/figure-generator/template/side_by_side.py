"""Puts a reference picture and a render of your figure side by side (needs Pillow).

    python side_by_side.py reference.png render.png --out compare.png

Use it at the first checkpoint: look at the result and compare the head, the eyes, the collar, the
belly, the arms, the legs and the shoes. The reference is only shown next to your figure to compare
proportions; nothing of it ends up in the figure.

`render.png` is a render of one cell of the contact sheet, for example
    node figures.mjs --dir <figure> --set tops --clip 16,53,200,360 --scale 2.5 --out render.png
(the cell is 200 px wide; its height is 200 * H / W plus a label, which is cropped off here).
"""

import argparse
import sys

from PIL import Image


def side_by_side(reference: Image.Image, render: Image.Image, height: int = 900) -> Image.Image:
    reference = reference.convert("RGB")
    render = render.convert("RGB")
    reference = reference.resize((round(reference.width * height / reference.height), height))
    # the label under the figure takes about 8 % of the cell
    render = render.crop((0, 0, render.width, round(render.height * 0.92)))
    render = render.resize((round(render.width * height / render.height), height))
    sheet = Image.new("RGB", (reference.width + render.width + 30, height), "#cccccc")
    sheet.paste(reference, (0, 0))
    sheet.paste(render, (reference.width + 30, 0))
    return sheet


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("reference")
    parser.add_argument("render")
    parser.add_argument("--out", required=True)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args(argv)
    sheet = side_by_side(Image.open(args.reference), Image.open(args.render), args.height)
    sheet.save(args.out)
    print(args.out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
