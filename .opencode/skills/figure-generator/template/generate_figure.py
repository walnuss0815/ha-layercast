"""Layercast figure template: draws a whole figure as SVG (figure.json, the body, 18 layers).

    python generate_figure.py --out <folder> [--name "My figure"]

Copy this file next to your figure (for a private one: local/tools/), then change the PARAMETERS
and, to draw the character, `head()` and `EXTRAS`. The defaults draw a plain person.

All layers share one canvas (W x H). The body is described by a few numbers (the torso profile,
the arm line, the legs). Every top is built from them: a sleeve is a tube around the arm, so the
arm always leaves through the cuff, and every outer layer is a bit bigger than the one it covers.
The script checks that at the end and exits with 1 if a layer pokes out of the layer over it, the
same check as tests/test_figures.py.
"""

import argparse
import json
import math
import sys
from pathlib import Path

# ==================================================================================== PARAMETERS
W, H = 160, 320  # the canvas; the card scales it, so only the proportions matter
CX = W / 2

# --- colours of the body ---------------------------------------------------------------------
SKIN, SKIN_LINE = "#f3c9a8", "#c58f6b"
HAIR = "#5d4037"
EYE = "#37474f"
BRIEFS, BRIEFS_LINE = "#cfd8dc", "#90a4ae"

# --- the head. Hats sit above HAT_BAND_Y, which must be above the eyes --------------------------
HEAD_CY, HEAD_RX, HEAD_RY = 40, 22, 25  # centre and radii of the head
EYE_Y, EYE_DX, EYE_R = 44, 9, 2.4  # eyes: height, distance from the middle, size
HAT_BAND_Y = 36  # lower edge of a beanie band and of the dome of a cap
HAT_TOP_Y = 6  # top of a beanie
LENS_W, LENS_H, LENS_DX = 16, 11, 11  # sunglasses: one lens, and its distance from the middle

# --- the torso: (y, half width) keys, a smooth curve through them ------------------------------
TORSO = [(76, 14), (84, 20), (100, 24), (130, 25), (160, 25), (172, 24), (260, 24)]
NECK_Y = 76  # where the head ends: every top starts its neckline here
NECK_X = 18  # half width of that neckline
NECK_W = 20  # width of the neck of the body (0 for a figure without a neck)
CROTCH_Y = 172  # the torso (and the briefs) end here, below it the legs
CROTCH_DROP = 22  # where the legs of trousers part, below CROTCH_Y

# --- the arm: a line from the shoulder to the wrist; the hand is a little further ---------------
SHOULDER = (CX - 25, 92)
WRIST = (CX - 48, 168)
ARM_R = 9  # radius of the arm, outline included
HAND_R, HAND_AT = 10, 8  # the hand: its size, and how far beyond the wrist (along the arm)

# --- the legs: two thick lines; the middle of a leg is LEG_X from the middle of the figure ------
LEG_X, LEG_W = 12, 22
LEG_BOTTOM = 284  # the shoes start here
SHOE_TOP, SHOE_BOTTOM = 280, 300
SHOE_OUT = 8  # how far a shoe reaches beyond the leg, to the outside
UMBRELLA_LEN = 114  # the length of the closed umbrella from the hand down (the canvas must fit it)
BOOT_TOP, RAIN_BOOT_TOP = 262, 236  # the top of the shaft

# --- the tops. `r`: how far the sleeve reaches beyond the arm, `m`: how far the body of the top
# reaches beyond the torso, `t`: where the sleeve ends along the arm (0 shoulder, 1 wrist). An outer
# layer must be bigger than every layer worn under it: r, m, hem and `lift` (how much higher its
# shoulders are) grow from the t-shirt to the rain jacket, which is the biggest. ----------------
TOPS = {
    "tshirt": dict(
        fill="#4fc3f7", line="#0277bd", r=3.5, m=2.5, t=0.38, hem=166, short=True, lift=0
    ),
    "long_sleeve": dict(fill="#81c784", line="#2e7d32", r=3.5, m=2.5, t=0.95, hem=168, lift=0),
    "sweater": dict(fill="#ffb74d", line="#e65100", r=5, m=3.5, t=0.96, hem=174, lift=1, dip=90),
    "jacket": dict(fill="#7986cb", line="#283593", r=8.5, m=7, t=0.97, hem=184, lift=3, dip=92),
    "winter_coat": dict(
        fill="#a1887f", line="#4e342e", r=11, m=10, t=0.98, hem=200, lift=5, dip=92
    ),
    "rain_jacket": dict(
        fill="#ffd54f", line="#f57f17", r=13.5, m=13, t=1.0, hem=208, lift=7, dip=96
    ),
}
LIGHT_JACKET = dict(
    fill="#90a4ae", line="#455a64", r=7, m=5.5, t=0.96, hem=178, lift=2
)  # open at the front

# --- the rest of the wardrobe -------------------------------------------------------------------
TROUSERS = dict(fill="#546e7a", line="#263238", waist=158)
SHORTS = dict(fill="#c9a66b", line="#6d4c41", hem=218)
THERMAL = dict(fill="#455a64", line="#1c313a")
SNEAKERS = dict(fill="#fafafa", line="#455a64", sole="#e53935")
BOOTS = dict(fill="#6d4c41", line="#3e2723")
RAIN_BOOTS = dict(fill="#fdd835", line="#f57f17")
BEANIE = dict(fill="#ab47bc", line="#6a1b9a", band="#ce93d8", bobble="#f3e5f5")
SUN_CAP = dict(fill="#ef5350", line="#b71c1c", brim="#c62828")
SUNGLASSES = dict(fill="#263238", line="#000000", glint="#cfd8dc")
GLOVES = dict(fill="#26a69a", line="#00695c", cuff="#b2dfdb")
UMBRELLA = dict(fill="#ef5350", line="#b71c1c", handle="#455a64")

# --- extra drawing on top of a layer, to make it the character's own: layer name -> svg. --------
# Fill it in `character()` (below), as it can use the helpers.
EXTRAS: dict[str, str] = {}

# ============================================================================== END OF PARAMETERS

OUT = Path("figure")
POLYS: dict[str, list] = {}  # the outlines of the tops, for the nesting check

ARM_LEN = math.hypot(WRIST[0] - SHOULDER[0], WRIST[1] - SHOULDER[1])
D = ((WRIST[0] - SHOULDER[0]) / ARM_LEN, (WRIST[1] - SHOULDER[1]) / ARM_LEN)  # along the arm
P = (abs(D[1]), abs(D[0]))  # across the arm, towards the body (right and down)
HAND = (WRIST[0] + HAND_AT * D[0], WRIST[1] + HAND_AT * D[1])
LEG_EDGE = LEG_X + LEG_W / 2  # the outer edge of a leg, from the middle of the figure


def hw(y: float) -> float:
    """Half width of the torso at height y: a smooth curve through the TORSO keys."""
    keys = TORSO
    if y <= keys[0][0]:
        return keys[0][1]
    if y >= keys[-1][0]:
        return keys[-1][1]
    i = next(i for i in range(len(keys) - 1) if keys[i][0] <= y <= keys[i + 1][0])

    def slope(j):  # the tangent at key j
        a, b = keys[max(j - 1, 0)], keys[min(j + 1, len(keys) - 1)]
        return (b[1] - a[1]) / (b[0] - a[0]) if b[0] != a[0] else 0

    (y0, h0), (y1, h1) = keys[i], keys[i + 1]
    dy = y1 - y0
    t = (y - y0) / dy
    m0, m1 = slope(i) * dy, slope(i + 1) * dy
    return (
        (2 * t**3 - 3 * t**2 + 1) * h0
        + (t**3 - 2 * t**2 + t) * m0
        + (-2 * t**3 + 3 * t**2) * h1
        + (t**3 - t**2) * m1
    )


def edge(y: float, m: float = 0.0) -> float:
    """x of the left edge of the torso at height y, with a margin m (a garment over it)."""
    return CX - (hw(y) + m)


def mirror(p):
    return (W - p[0], p[1])


def n(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def pt(p) -> str:
    return f"{n(p[0])} {n(p[1])}"


def arm_point(t: float):
    """The point at t along the arm (0 shoulder, 1 wrist)."""
    return (SHOULDER[0] + (WRIST[0] - SHOULDER[0]) * t, SHOULDER[1] + (WRIST[1] - SHOULDER[1]) * t)


def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">\n{body}</svg>\n'


def write(name: str, body: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text(svg(body))


def stroke_attrs(stroke, width, fill="none"):
    return (
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}" '
        'stroke-linejoin="round" stroke-linecap="round"'
    )


def path(points, stroke, fill="none", width=2.5, close=True) -> str:
    d = "M" + " L".join(pt(p) for p in points) + ("Z" if close else "")
    return f'  <path d="{d}" {stroke_attrs(stroke, width, fill)}/>\n'


def line(a, b, stroke, width=2.0) -> str:
    return f'  <path d="M{pt(a)}L{pt(b)}" {stroke_attrs(stroke, width)}/>\n'


def both(a, b, stroke, width=2.0) -> str:
    """The same line on both sides: the left one a-b, the right one mirrored."""
    return line(a, b, stroke, width) + line(mirror(a), mirror(b), stroke, width)


def mirrored_use(group_id: str, body: str) -> str:
    """A group drawn for the left side, and used again mirrored for the right side."""
    return (
        f'  <defs>\n  <g id="{group_id}">\n{body}  </g>\n  </defs>\n'
        f'  <use href="#{group_id}"/>\n'
        f'  <use href="#{group_id}" transform="translate({W} 0) scale(-1 1)"/>\n'
    )


# ===================================================================================== THE BODY
def head() -> str:
    """The head, as svg: REPLACE THIS to draw the character (a face, hair, a nose, ears).

    Keep the face where HEAD_CY/EYE_Y say, so the hats and sunglasses fit: hats sit above
    HAT_BAND_Y, sunglasses over the eyes at EYE_Y.
    """
    s = (
        f'  <ellipse cx="{n(CX)}" cy="{HEAD_CY}" rx="{HEAD_RX}" ry="{HEAD_RY}" '
        f'fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2"/>\n'
    )
    # the hair: the top of the head down to a hairline
    dy = 6
    dx = HEAD_RX * math.sqrt(1 - (dy / HEAD_RY) ** 2)
    s += (
        f'  <path d="M{n(CX - dx)} {n(HEAD_CY - dy)}A{HEAD_RX} {HEAD_RY} 0 0 1 '
        f"{n(CX + dx)} {n(HEAD_CY - dy)}Q{n(CX)} {n(HEAD_CY - dy - 12)} {n(CX - dx)} "
        f'{n(HEAD_CY - dy)}Z" fill="{HAIR}"/>\n'
    )
    for side in (-1, 1):
        s += f'  <circle cx="{n(CX + side * EYE_DX)}" cy="{EYE_Y}" r="{EYE_R}" fill="{EYE}"/>\n'
    mouth_y = EYE_Y + 10
    s += (
        f'  <path d="M{n(CX - 6)} {mouth_y}Q{n(CX)} {mouth_y + 5} {n(CX + 6)} {mouth_y}" '
        f'fill="none" stroke="#8d5b4c" stroke-width="2" stroke-linecap="round"/>\n'
    )
    return s


def body() -> str:
    s = ""
    # arms and hands (the left one; the right one is the same mirrored)
    arm = (
        f'    <path d="M{pt(SHOULDER)}L{pt(WRIST)}" fill="none" stroke="{SKIN_LINE}" '
        f'stroke-width="{n(ARM_R * 2)}" stroke-linecap="round"/>\n'
        f'    <path d="M{pt(SHOULDER)}L{pt(WRIST)}" fill="none" stroke="{SKIN}" '
        f'stroke-width="{n(ARM_R * 2 - 3)}" stroke-linecap="round"/>\n'
        f'    <circle cx="{n(HAND[0])}" cy="{n(HAND[1])}" r="{HAND_R}" fill="{SKIN}" '
        f'stroke="{SKIN_LINE}" stroke-width="2"/>\n'
    )
    s += mirrored_use("arm", arm)
    # legs
    for side in (1, -1):
        x = CX - side * LEG_X
        top_y = CROTCH_Y - 20
        for stroke, width in ((SKIN_LINE, LEG_W + 3), (SKIN, LEG_W)):
            s += (
                f'  <path d="M{n(x)} {top_y}L{n(x)} {LEG_BOTTOM}" fill="none" stroke="{stroke}" '
                f'stroke-width="{width}" stroke-linecap="round"/>\n'
            )
    # the torso, then the neck over its top edge (the head is drawn last, over the neck)
    left = [(edge(y), y) for y in range(NECK_Y - 8, CROTCH_Y, 4)] + [(edge(CROTCH_Y), CROTCH_Y)]
    s += path(left + [mirror(p) for p in reversed(left)], SKIN_LINE, SKIN, 2)
    if NECK_W:
        s += (
            f'  <rect x="{n(CX - NECK_W / 2)}" y="{NECK_Y - 10}" width="{NECK_W}" height="24" '
            f'fill="{SKIN}" stroke="{SKIN_LINE}" stroke-width="2"/>\n'
        )
    # briefs, so the figure is not bare when no trousers match
    top_y, hip = CROTCH_Y - 18, LEG_EDGE - 4
    briefs = [
        (CX - hw(top_y), top_y),
        (CX + hw(top_y), top_y),
        (CX + hw(CROTCH_Y), CROTCH_Y),
        (CX + hip, CROTCH_Y + 9),
        (CX, CROTCH_Y + 1),
        (CX - hip, CROTCH_Y + 9),
        (CX - hw(CROTCH_Y), CROTCH_Y),
    ]
    s += path(briefs, BRIEFS_LINE, BRIEFS, 1.8)
    return s + head()


# ======================================================================================== TOPS
def scan(fn, lo, hi, step=0.1):
    """The first x in [lo, hi] where fn goes from negative to non-negative."""
    prev = fn(lo)
    x = lo
    while x < hi:
        x += step
        cur = fn(x)
        if prev < 0 <= cur:
            return x
        prev = cur
    return None


def sleeve(r, t, m, short=False, shoulder_y=None):
    """The left sleeve and shoulder of a top: tip, outer cuff corner, inner cuff corner, armpit.

    The sleeve is a tube of radius `r` around the arm. If it is so wide that it runs into the
    torso, there is no gap under the arm and the armpit is None.
    """
    ys = shoulder_y if shoulder_y is not None else SHOULDER[1] - 6
    c = arm_point(t)
    outer = (c[0] - r * P[0], c[1] - r * P[1])
    # the outer edge of the tube runs on, up along the arm, to the height of the shoulder
    up = (outer[1] - ys) / D[1]
    tip = (outer[0] - D[0] * up, ys)
    # along the cuff line, across the arm, to the edge of the torso
    s_cut = scan(lambda s: (outer[0] + P[0] * s) - edge(outer[1] + P[1] * s, m), 0, 80)
    cut = (outer[0] + P[0] * s_cut, outer[1] + P[1] * s_cut)
    if short or s_cut < 2 * r - 0.5:
        return tip, outer, cut, None
    inner = (c[0] + r * P[0], c[1] + r * P[1])
    reach = (inner[1] - ys - 8) / D[1]
    u = scan(lambda u: (inner[0] - D[0] * u) - edge(inner[1] - D[1] * u, m), 0, reach)
    if u is None:
        return tip, outer, cut, None
    return tip, outer, inner, (inner[0] - D[0] * u, inner[1] - D[1] * u)


def outline(spec: dict, open_front: bool = False) -> list:
    """The outline of a top (its left half when open at the front, else the whole)."""
    r, m, hem = ARM_R + spec["r"], spec["m"], spec["hem"]
    shoulder_y = SHOULDER[1] - 6 - spec["lift"]
    tip, outer, inner, armpit = sleeve(r, spec["t"], m, spec.get("short", False), shoulder_y)
    left = [(CX - NECK_X, NECK_Y), tip, outer, inner]
    if armpit:
        left.append(armpit)
    start = (armpit or inner)[1]
    left += [(edge(y, m), y) for y in range(int(start // 6 * 6 + 6), hem, 6)]
    left.append((edge(hem, m), hem))
    if open_front:
        return left + [(CX - 7, hem), (CX - 9, NECK_Y + 24), (CX - 12, NECK_Y + 4)]
    return left + [mirror(p) for p in reversed(left)]


def cuff_line(spec: dict, up: float, stroke: str, width: float = 2.0) -> str:
    """A line across the sleeve, `up` units above its cuff (both sleeves)."""
    r = ARM_R + spec["r"]
    c = arm_point(spec["t"])
    c = (c[0] - D[0] * up, c[1] - D[1] * up)
    return both(
        (c[0] - r * P[0], c[1] - r * P[1]), (c[0] + r * P[0], c[1] + r * P[1]), stroke, width
    )


def top(name: str, extra: str = "") -> None:
    """Writes a top: its outline, the neckline, and `extra` drawing (then EXTRAS[name])."""
    spec = TOPS[name]
    points = outline(spec)
    POLYS[name] = points
    dip = spec.get("dip", 88)
    d = "M" + " L".join(pt(p) for p in points) + f" Q{n(CX)} {dip} {pt(points[0])}Z"
    line_c = spec["line"]
    s = f'  <path d="{d}" {stroke_attrs(line_c, 2.5, spec["fill"])}/>\n'
    s += (
        f'  <path d="M{n(CX - NECK_X)} {NECK_Y}Q{n(CX)} {dip} {n(CX + NECK_X)} {NECK_Y}" '
        f"{stroke_attrs(line_c, 2.5)}/>\n"
    )
    write(name, s + extra + EXTRAS.get(name, ""))


def tops() -> None:
    t = TOPS
    top("tshirt")
    top("long_sleeve", cuff_line(t["long_sleeve"], 4, t["long_sleeve"]["line"]))
    sw = t["sweater"]
    rib = line(
        (edge(sw["hem"] - 2, sw["m"]) + 1, sw["hem"] - 2),
        (CX + hw(sw["hem"] - 2) + sw["m"] - 1, sw["hem"] - 2),
        sw["line"],
    )
    top("sweater", cuff_line(sw, 4, sw["line"]) + cuff_line(sw, 8, sw["line"], 1.5) + rib)

    # the jacket: a zip and two pockets
    j = t["jacket"]
    py = j["hem"] - 22
    pockets = both((edge(py, j["m"]) + 8, py), (CX - 12, py), j["line"], 2.5)
    top(
        "jacket",
        cuff_line(j, 5, j["line"]) + line((CX, 94), (CX, j["hem"]), j["line"], 2.5) + pockets,
    )

    # the winter coat: quilting and a fur collar
    c = t["winter_coat"]
    quilt = "".join(
        line((edge(y, c["m"]) + 1.5, y), (CX + hw(y) + c["m"] - 1.5, y), c["line"], 1.8)
        for y in range(NECK_Y + 36, c["hem"] - 8, 26)
    )
    fur = path(
        [
            (CX - NECK_X - 10, NECK_Y + 3),
            (CX - 2, NECK_Y + 25),
            (CX + 2, NECK_Y + 25),
            (CX + NECK_X + 10, NECK_Y + 3),
            (CX + NECK_X + 5, NECK_Y - 2),
            (CX, NECK_Y + 12),
            (CX - NECK_X - 5, NECK_Y - 2),
        ],
        "#8d99ae",
        "#eceff1",
        2.2,
    )
    top(
        "winter_coat",
        quilt
        + cuff_line(c, 6, c["line"])
        + line((CX, NECK_Y + 22), (CX, c["hem"]), c["line"], 2.5)
        + fur,
    )

    # the rain jacket: the biggest layer, with a hood
    r = t["rain_jacket"]
    hood = path(
        [
            (CX - NECK_X - 18, NECK_Y + 14),
            (CX - NECK_X - 9, NECK_Y + 6),
            (CX - 2, NECK_Y + 23),
            (CX + 2, NECK_Y + 23),
            (CX + NECK_X + 9, NECK_Y + 6),
            (CX + NECK_X + 18, NECK_Y + 14),
            (CX, NECK_Y + 34),
        ],
        r["line"],
        "#ffca28",
        2.2,
    )
    pocket_y, hem_line = r["hem"] - 30, r["hem"] - 6
    top(
        "rain_jacket",
        line((CX, NECK_Y + 28), (CX, r["hem"]), r["line"], 2.5)
        + cuff_line(r, 5, r["line"])
        + both((edge(pocket_y, r["m"]) + 8, pocket_y), (CX - 12, pocket_y), r["line"], 2.5)
        + line(
            (edge(hem_line, r["m"]) + 1.5, hem_line),
            (CX + hw(hem_line) + r["m"] - 1.5, hem_line),
            r["line"],
            1.8,
        )
        + hood,
    )
    light_jacket()


def light_jacket() -> None:
    """The open jacket: the left half, and the right half is the same mirrored."""
    spec = LIGHT_JACKET
    half = outline(spec, open_front=True)
    POLYS["light_jacket"] = half
    line_c = spec["line"]
    r = ARM_R + spec["r"]
    c = arm_point(spec["t"])
    c = (c[0] - D[0] * 5, c[1] - D[1] * 5)
    a, b = (c[0] - r * P[0], c[1] - r * P[1]), (c[0] + r * P[0], c[1] + r * P[1])
    py = spec["hem"] - 26
    d = "M" + " L".join(pt(p) for p in half) + "Z"
    inner = (
        f'    <g stroke="{line_c}" stroke-width="2.5" stroke-linejoin="round" '
        'stroke-linecap="round">\n'
        f'      <path d="{d}" fill="{spec["fill"]}"/>\n'
        f'      <path d="M{pt(a)}L{pt(b)}M{pt((edge(py, spec["m"]) + 7, py))}L{pt((CX - 18, py))}" '
        'fill="none" stroke-width="2"/>\n'
        "    </g>\n"
    )
    write("light_jacket", mirrored_use("h", inner) + EXTRAS.get("light_jacket", ""))


# ===================================================================================== LEGS, FEET
def leg_outline(hem: float, flare: float = 0.0) -> list:
    """Trousers or shorts: the waist, down the outside of the body and the leg, to the hem."""
    outer = LEG_EDGE + 2.5 + flare
    inner = max(0.8, min(1.5, LEG_X - LEG_W / 2 - 2))  # the gap between the legs, halved
    left = [(edge(y, 1.5), y) for y in range(TROUSERS["waist"], CROTCH_Y, 6)]
    left += [(CX - outer, CROTCH_Y + 4), (CX - outer, hem), (CX - inner, hem)]
    left += [(CX - 1, CROTCH_Y + CROTCH_DROP)]
    return left + [mirror(p) for p in reversed(left)]


def legs() -> None:
    waist = TROUSERS["waist"]
    for name, spec, hem in (
        ("trousers", TROUSERS, LEG_BOTTOM),
        ("shorts", SHORTS, SHORTS["hem"]),
        ("thermal_trousers", THERMAL, LEG_BOTTOM + 2),
    ):
        belt_y = waist + 7
        belt = line((edge(belt_y, 1.5) + 1, belt_y), (CX + hw(belt_y) + 0.5, belt_y), spec["line"])
        ribs = ""
        if name == "thermal_trousers":
            for y in range(CROTCH_Y + CROTCH_DROP, hem - 8, 18):
                ribs += line((CX - LEG_EDGE - 1, y), (CX - 3, y), spec["line"], 1.5)
                ribs += line((CX + 3, y), (CX + LEG_EDGE + 1, y), spec["line"], 1.5)
        flare = 1.5 if name == "thermal_trousers" else 0.0
        outline_ = path(leg_outline(hem, flare), spec["line"], spec["fill"], 2.5)
        write(name, outline_ + belt + ribs + EXTRAS.get(name, ""))


def shoes() -> None:
    # a shoe spans from the outside of the leg (and a bit beyond) to just before the middle
    x0 = CX - LEG_EDGE - SHOE_OUT
    sw = min(CX - 1.5, CX - LEG_X + LEG_W / 2 + 1) - x0
    snk = SNEAKERS
    body_ = (
        f'    <rect x="{n(x0)}" y="{SHOE_TOP}" width="{n(sw)}" height="{SHOE_BOTTOM - SHOE_TOP}" '
        f'rx="10" fill="{snk["fill"]}" stroke="{snk["line"]}" stroke-width="2.5"/>\n'
        f'    <rect x="{n(x0 + 1)}" y="{SHOE_BOTTOM - 7}" width="{n(sw - 2)}" height="6" rx="3" '
        f'fill="{snk["sole"]}"/>\n'
        f'    <path d="M{n(x0 + sw / 2 - 6)} {SHOE_TOP + 7}H{n(x0 + sw / 2 + 6)}" fill="none" '
        f'stroke="{snk["line"]}" stroke-width="2" stroke-linecap="round"/>\n'
    )
    write("sneakers", mirrored_use("s", body_))
    for name, spec, top_y in (
        ("boots", BOOTS, BOOT_TOP),
        ("rain_boots", RAIN_BOOTS, RAIN_BOOT_TOP),
    ):
        left, right = CX - LEG_X - LEG_W / 2 - 1, CX - LEG_X + LEG_W / 2 + 1  # the shaft
        toe = left - 3
        bottom = SHOE_BOTTOM
        boot = (
            f'    <path d="M{n(left)} {top_y}H{n(right)}V{bottom - 12}'
            f"Q{n(right + 2)} {bottom - 10} "
            f"{n(right + 2)} {bottom - 5}V{bottom}H{n(toe)}V{bottom - 6}Q{n(toe)} {bottom - 12} "
            f'{n(left)} {bottom - 13}Z" fill="{spec["fill"]}" stroke="{spec["line"]}" '
            'stroke-width="2.5" stroke-linejoin="round"/>\n'
            f'    <path d="M{n(left)} {top_y + 8}H{n(right)}M{n(toe)} {bottom - 3}H{n(right + 2)}" '
            f'fill="none" stroke="{spec["line"]}" stroke-width="2.5"/>\n'
        )
        write(name, mirrored_use("b", boot))


# ============================================================== HEAD ITEMS, HANDS, UMBRELLA
def accessories() -> None:
    hw_ = HEAD_RX + 4  # half width of a hat
    b = BEANIE
    band_y = HAT_BAND_Y - 11
    y0 = HAT_BAND_Y - 8
    ctrl = (
        y0 + (HAT_TOP_Y - y0) / 0.75
    )  # a cubic curve reaches 3/4 of the way to its control points
    write(
        "hat",
        f'  <g stroke="{b["line"]}" stroke-width="2.5" stroke-linejoin="round">\n'
        f'    <path d="M{n(CX - hw_ + 2)} {y0}C{n(CX - hw_ + 2)} {n(ctrl)} {n(CX + hw_ - 2)} '
        f'{n(ctrl)} {n(CX + hw_ - 2)} {y0}Z" fill="{b["fill"]}"/>\n'
        f'    <path d="M{n(CX - 12)} {y0 - 15}V{y0 - 1}M{n(CX)} {y0 - 19}V{y0 - 1}'
        f'M{n(CX + 12)} {y0 - 15}V{y0 - 1}" fill="none" stroke-width="2"/>\n'
        f'    <rect x="{n(CX - hw_)}" y="{band_y}" width="{n(2 * hw_)}" height="11" rx="5" '
        f'fill="{b["band"]}"/>\n'
        f'    <circle cx="{n(CX)}" cy="{HAT_TOP_Y + 2}" r="5.5" fill="{b["bobble"]}"/>\n'
        "  </g>\n",
    )
    c = SUN_CAP
    y0 = HAT_BAND_Y - 6
    ctrl = y0 + (HAT_TOP_Y + 2 - y0) / 0.75
    write(
        "sun_cap",
        f'  <g stroke="{c["line"]}" stroke-width="2.5" stroke-linejoin="round">\n'
        f'    <path d="M{n(CX - hw_ + 3)} {y0}C{n(CX - hw_ + 3)} {n(ctrl)} {n(CX + hw_ - 3)} '
        f'{n(ctrl)} {n(CX + hw_ - 3)} {y0}Z" fill="{c["fill"]}"/>\n'
        f'    <path d="M{n(CX - hw_)} {y0 + 1}Q{n(CX)} {y0 + 16} {n(CX + hw_)} {y0 + 1}'
        f'L{n(CX + hw_ - 2)} {y0 - 2}Q{n(CX)} {y0 + 4} {n(CX - hw_ + 2)} {y0 - 2}Z" '
        f'fill="{c["brim"]}"/>\n'
        "  </g>\n",
    )
    g = SUNGLASSES
    lx = [CX - LENS_DX - LENS_W / 2, CX + LENS_DX - LENS_W / 2]
    ly = EYE_Y - LENS_H / 2 + 0.5
    lenses = "".join(
        f'    <rect x="{n(x)}" y="{n(ly)}" width="{LENS_W}" height="{LENS_H}" rx="5"/>\n'
        for x in lx
    )
    bridge_y = EYE_Y - 1
    write(
        "sunglasses",
        f'  <g fill="{g["fill"]}" stroke="{g["line"]}" stroke-width="2" stroke-linejoin="round">\n'
        f"{lenses}  </g>\n"
        f'  <path d="M{n(lx[0] + LENS_W)} {bridge_y}Q{n(CX)} {bridge_y - 2} {n(lx[1])} {bridge_y}'
        f"M{n(lx[0])} {bridge_y}L{n(lx[0] - 3)} {bridge_y - 2}M{n(lx[1] + LENS_W)} {bridge_y}"
        f'L{n(lx[1] + LENS_W + 3)} {bridge_y - 2}" fill="none" stroke="{g["line"]}" '
        'stroke-width="2" stroke-linecap="round"/>\n'
        f'  <path d="M{n(lx[0] + 3)} {bridge_y + 1}L{n(lx[0] + 7)} {bridge_y}'
        f'M{n(lx[1] + 3)} {bridge_y + 1}L{n(lx[1] + 7)} {bridge_y}" fill="none" '
        f'stroke="{g["glint"]}" stroke-width="1.5" stroke-linecap="round"/>\n',
    )
    # mittens: under the sleeves (z 25), so only the hand and a bit of the cuff show
    gl = GLOVES
    c0, c1 = arm_point(0.88), arm_point(1.04)
    wide = HAND_R + 1
    cuff = [
        (c0[0] - wide * P[0], c0[1] - wide * P[1]),
        (c0[0] + wide * P[0], c0[1] + wide * P[1]),
        (c1[0] + wide * P[0], c1[1] + wide * P[1]),
        (c1[0] - wide * P[0], c1[1] - wide * P[1]),
    ]
    glove = (
        f'    <circle cx="{n(HAND[0])}" cy="{n(HAND[1] + 2)}" r="{HAND_R + 3}" fill="{gl["fill"]}" '
        f'stroke="{gl["line"]}" stroke-width="2.5"/>\n'
        + path(cuff, gl["line"], gl["cuff"], 2.5).replace("  <path", "    <path", 1)
    )
    write("gloves", mirrored_use("g", glove))
    # the umbrella hangs closed from the right hand
    u = UMBRELLA
    hx, hy = W - HAND[0], HAND[1]
    tip, mid = hy + UMBRELLA_LEN, hy + UMBRELLA_LEN // 2
    write(
        "umbrella",
        f'  <path d="M{n(hx)} {n(hy - 12)}V{n(hy - 20)}Q{n(hx)} {n(hy - 28)} {n(hx + 7)} '
        f'{n(hy - 28)}Q{n(hx + 14)} {n(hy - 28)} {n(hx + 14)} {n(hy - 21)}" fill="none" '
        f'stroke="{u["handle"]}" stroke-width="3.5" stroke-linecap="round"/>\n'
        f'  <path d="M{n(hx - 6)} {n(hy + 8)}Q{n(hx - 8)} {n(mid)} {n(hx)} {n(tip)}'
        f'Q{n(hx + 8)} {n(mid)} {n(hx + 6)} {n(hy + 8)}Z" fill="{u["fill"]}" '
        f'stroke="{u["line"]}" stroke-width="2.5" stroke-linejoin="round"/>\n'
        f'  <path d="M{n(hx)} {n(hy + 10)}Q{n(hx - 1)} {n(mid)} {n(hx)} {n(tip - 4)}'
        f'M{n(hx - 5)} {n(hy + UMBRELLA_LEN * 3 // 7)}H{n(hx + 5)}" fill="none" '
        f'stroke="{u["line"]}" stroke-width="2" stroke-linecap="round"/>\n'
        f'  <path d="M{n(hx)} {n(tip)}V{n(tip + 7)}" fill="none" stroke="#263238" '
        'stroke-width="3" stroke-linecap="round"/>\n',
    )


# ====================================================================================== FIGURE.JSON
Z = {  # the stacking order: higher is in front
    "trousers": 10,
    "shorts": 10,
    "thermal_trousers": 10,
    "sneakers": 20,
    "boots": 20,
    "rain_boots": 20,
    "gloves": 25,  # under the sleeves
    "tshirt": 30,
    "long_sleeve": 30,
    "sweater": 30,
    "light_jacket": 40,
    "jacket": 40,
    "winter_coat": 40,
    "rain_jacket": 45,
    "hat": 70,
    "sun_cap": 70,
    "sunglasses": 75,
    "umbrella": 80,
}


def figure_json(name: str) -> None:
    data = {
        "name": name,
        "width": W,
        "height": H,
        "base": "body.svg",
        "layers": {key: {"file": f"{key}.svg", "z": z} for key, z in Z.items()},
    }
    (OUT / "figure.json").write_text(json.dumps(data, indent=2) + "\n")


# ======================================================================================== THE CHECK
def inside(poly, q) -> bool:
    odd = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y1 > q[1]) != (y2 > q[1]) and q[0] < x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1):
            odd = not odd
    return odd


def edge_distance(poly, q) -> float:
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        dx, dy = x2 - x1, y2 - y1
        t = max(0, min(1, ((q[0] - x1) * dx + (q[1] - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(q[0] - x1 - t * dx, q[1] - y1 - t * dy))
    return best


def margin(under, over) -> float:
    """How far the outline `under` lies inside `over` (negative: it pokes out).

    The neckline is left out (the first 2 units below the top of `under`): every top starts at the
    same neck, so there the outlines touch.
    """
    neck = min(y for _, y in under) + 2
    worst = float("inf")
    for (x1, y1), (x2, y2) in zip(under, under[1:] + under[:1], strict=True):
        for i in range(10):
            q = (x1 + (x2 - x1) * i / 10, y1 + (y2 - y1) * i / 10)
            if q[1] <= neck:
                continue
            d = edge_distance(over, q)
            worst = min(worst, d if inside(over, q) else -d)
    return worst


def check() -> bool:
    """Every top must lie inside the tops that are worn over it, by at least 0.5."""
    ok = True
    pairs = [
        (b, o)
        for b in ("tshirt", "long_sleeve", "sweater")
        for o in ("jacket", "winter_coat", "rain_jacket")
    ]
    pairs += [("jacket", "rain_jacket"), ("winter_coat", "rain_jacket")]
    for under, over in pairs:
        m = margin(POLYS[under], POLYS[over])
        flag = "" if m >= 0.5 else "   <-- too small: make the outer one bigger (r, m, hem)"
        ok &= not flag
        print(f"  {under:12} in {over:12} {m:5.1f}{flag}", file=sys.stderr)
    half = POLYS["light_jacket"]
    m = min(
        margin(half, POLYS["rain_jacket"]),
        margin([mirror(p) for p in half], POLYS["rain_jacket"]),
    )
    flag = "" if m >= 0.5 else "   <-- too small"
    print(f"  light_jacket in rain_jacket {m:5.1f}{flag}", file=sys.stderr)
    return ok and m >= 0.5


def character() -> None:
    """Hook for a figure of a character: fill EXTRAS and replace head(), for example

    EXTRAS["tshirt"] = collar_svg      # drawn on top of the t-shirt layer
    """


def main(argv=None) -> int:
    global OUT
    parser = argparse.ArgumentParser(description="Draws a Layercast figure as SVG layers.")
    parser.add_argument("--out", required=True, type=Path, help="folder for figure.json and svgs")
    parser.add_argument("--name", default="Figure", help="the name in figure.json")
    args = parser.parse_args(argv)
    OUT = args.out
    OUT.mkdir(parents=True, exist_ok=True)
    character()
    write("body", body())
    tops()
    legs()
    shoes()
    accessories()
    figure_json(args.name)
    print(f"wrote {len(list(OUT.glob('*.svg')))} layers to {OUT}", file=sys.stderr)
    return 0 if check() else 1


if __name__ == "__main__":
    sys.exit(main())
