---
name: figure-generator
description: Layercast figure - create or redraw a figure (a person or character wearing the clothes) for the Layercast card, with every garment layer as SVG. Use when asked to make a figure, draw a character, add a new look, or fix how clothes fit on a figure. Covers what to ask the user, a parametric template, proportions measured from a reference picture, and the checks that prove the layers fit.
---

# Layercast figure generator

A figure is a folder with a `figure.json`, a body and one transparent SVG layer per garment, all on
the same canvas. The card stacks the layers for what the weather rules recommend. A figure can only
look right if every layer lines up with the body and every combination (sweater under jacket under
rain jacket, beanie with sunglasses) fits. **You cannot see what you draw: draw from parameters,
render, and look at the pictures** before saying it is done.

## 1. Read the contract (do not copy it from memory)
- `custom_components/layercast/const.py`: `IMAGES`, the image keys a layer can have.
- `custom_components/layercast/www/figures/neutral/figure.json`: the format and the `z` order.
- `README.md`, section "Figures": what the card does with a figure.
- `tests/test_figures.py`: the checks a figure must pass (files exist, tops nest).

Layers that exist: trousers, shorts, thermal_trousers, sneakers, boots, rain_boots, gloves, tshirt,
long_sleeve, sweater, light_jacket, jacket, winter_coat, rain_jacket, hat, sun_cap, sunglasses,
umbrella. A garment the figure does not draw is shown by the card as a small badge, so leaving
something out is allowed.

## 2. Ask the user (question tool), then state the defaults you use
| Ask | Why | Default if not answered |
|---|---|---|
| Who or what: a name or a description | the look | required |
| Reference picture(s): the whole figure, from the front, standing, plain background | proportions; without one you draw from memory and get them wrong | required for a known character |
| Distinctive features: head shape, hair, eyes, nose, mouth, beard, skin colour | what makes it recognisable | read off the picture |
| Signature outfit: which garments the character's own clothes replace (t-shirt = white shirt, trousers = blue trousers, sneakers = grey shoes) | the look on an ordinary day | plain t-shirt, trousers, sneakers |
| Colours of the other garments | consistency | propose a palette, ask to confirm |
| Garments to leave out | they become badges | none |
| Pose: arms hanging down or angled out | where hands, gloves and the umbrella go | as in the picture |
| Outline style | consistency with the card | thin outlines in a darker shade of each fill |
| Private or bundled | where the files go | private |

If a reference picture exists, the user's picture beats your memory of the character, and research
beats both. Write down the distinctive features before drawing.

## 3. Set up
```sh
mkdir -p local/tools local/figures/<name>          # private: local/ is git-ignored
cp .opencode/skills/figure-generator/template/generate_figure.py local/tools/generate_<name>.py
.venv/bin/python local/tools/generate_<name>.py --out local/figures/<name> --name "<Name>"
```
The template draws a plain person and runs a nesting check (exit code 1 if a layer pokes out).
Edit the copy: the PARAMETERS at the top, `head()`, and `character()` (which fills `EXTRAS`).
Never hand-write the layer SVGs: change a number and regenerate, so every layer stays consistent.

## 4. Measure the reference picture
```sh
.venv/bin/python .opencode/skills/figure-generator/template/measure_reference.py <picture> --rows 40
```
(needs Pillow, which the test requirements install). It prints the heights and widths as percentages
of the figure's height. Convert to the canvas: `y = TOP + y% * HEIGHT`, `x = CX + x% * HEIGHT`, with
HEIGHT about 280 of 320 (room for hats and the umbrella). Then fill the parameters:

| Measured | Parameter |
|---|---|
| top and bottom of the head, its widest row | `HEAD_CY`, `HEAD_RX`, `HEAD_RY` |
| where the collar or neck starts (no neck at all: `NECK_W = 0`, `NECK_Y` at the collar) | `NECK_Y`, `NECK_X`, `NECK_W` |
| the half width of the body at each height | `TORSO` keys `(y, half width)` |
| where the arm leaves the body and where the hand is | `SHOULDER`, `WRIST`, `ARM_R`, `HAND_R` |
| the two runs below the hips: their centres and width, where they part | `LEG_X`, `LEG_W`, `CROTCH_Y`, `CROTCH_DROP`, `LEG_BOTTOM` |
| the feet | `SHOE_TOP`, `SHOE_BOTTOM`, `SHOE_OUT` |
| the eyes (a big pair, touching) and sunglasses over them | `EYE_Y`, `EYE_DX`, `EYE_R`, `LENS_W`, `LENS_H`, `LENS_DX` |
| the canvas below the hand, for the umbrella | `UMBRELLA_LEN` (tip = hand y + length, must be < H) |
| the hem of the shirt | `TOPS["tshirt"]["hem"]`; grow the other hems from it |

The picture is only measured. Do not trace it, embed it or copy pixels or paths from it.
Distinct features that need drawing (a face, hair, a collar) go into `head()` and `EXTRAS`.

A figure that is wider than tall-and-thin needs a wider canvas: change `W` (the template centres
everything on `W / 2`), and keep `H` at 320.

## 5. Drawing rules (each of them was a visible bug once)
- **Sleeves** are tubes around the arm line, so the arm always leaves through the cuff. The
  template does this; do not draw a sleeve by hand that does not follow the arm.
- **Nesting:** every outer layer is at least 0.5 units bigger than everything worn under it
  (t-shirt, long sleeve, sweater < jacket < winter coat < rain jacket). The rain jacket is the
  largest. Grow `r`, `m`, `hem` and `lift` in `TOPS`, not the other way round.
- **Cuffs and shoulders must differ too.** Two tops with their cuff at the same `t` have the same
  cuff line, so the outer one does not cover the inner one: raise `t` a little for every outer
  layer (about 1 unit of arm length each), and raise its `lift` so its shoulder line leaves the
  shared neck point at a steeper angle. The generator's check names the pair that fails.
- **Necklines:** `dip` is how deep the neckline reaches. On a figure with no neck, a deep neckline
  shows a lot of skin: keep it shallow for sweaters and jackets, deep (a V) only for a collar.
- **Faces:** a thick dark outline around the eyes reads as glasses. Use a thin outline (about 1.3),
  and compare the face with the reference, not with your idea of it.
- **Gloves** are under the sleeves (`z` 25), so the cuff of a sleeve covers them.
- **Boots and shoes** are centred on the legs. Trousers follow the leg outline down to the hem,
  with no skin showing between trousers and shoes.
- **Hats** sit above `HAT_BAND_Y`, which must be above the eyes. Never cover the eyes. A beanie
  and sunglasses are worn together, so they must fit.
- **The light jacket is open** (the layer below shows), the **umbrella is closed** and hangs from
  the hand, the shorts end above the knee.
- **Everything shares the canvas.** Do not change `W`/`H` between layers. Layers are transparent
  except the garment. Colour the outline in a darker shade of the garment.
- A body that is not the default shape (a big belly, short legs, no neck) changes what is a good
  fit: after changing the body, re-check all layers, not only the one you worked on.

## 6. Check, and look
Render the contact sheet of every combination (`docs/screenshot/figures.mjs`), and look at it
(read the PNG):
```sh
cd docs/screenshot   # needs Playwright, see "Development" in the README
node figures.mjs --dir ../../local/figures/<name> --out /tmp/sheet.png            # everything
node figures.mjs --dir ../../local/figures/<name> --set tops --clip 16,53,420,420 --scale 3 --out /tmp/zoom.png
```
Sections: `tops`, `layers`, `legs`, `head`, `accessories`. `--clip x,y,w,h --scale n` zooms into a
region (cells are 200 px wide, starting at x 16, with 8 px between them).
**Zoom in** on arms and sleeves, the neck, the hem, the ankles, the eyes and the hands. Slivers of
2 units are visible on a screen. Do not trust the whole-sheet view alone.

```sh
LAYERCAST_FIGURE_DIRS=local/figures/<name> .venv/bin/python -m pytest tests/test_figures.py -q
```
At the first checkpoint, compare with the reference picture side by side and look at it:
```sh
node figures.mjs --dir ../../local/figures/<name> --set tops --clip 16,53,200,360 --scale 2.5 --out /tmp/cell.png
.venv/bin/python ../../.opencode/skills/figure-generator/template/side_by_side.py <reference> /tmp/cell.png --out /tmp/compare.png
```

Then see the figure in the card, in the timeline and the compact view:
`docs/screenshot/index.html?layout=compact&figure_url=/local/layercast/<name>/` (serve the figure
folder at that URL, as `docs/screenshot/render.mjs` does for the integration's `www` folder).

What to look for: skin showing at the armpit, a sleeve that does not meet the hand, a layer that
sticks out under the one over it, trousers that end above the shoes, a hat on the eyes, gloves over
the sleeves, anything cut off at the canvas edge, and whether the character is **recognisable**.

On NixOS a normal Chrome crashes headless. Use Playwright's browsers from nixpkgs
(`nix-build '<nixpkgs>' -A playwright-driver.browsers`) with `CHROMIUM_PATH` pointing at its
`chrome-headless-shell` and `CHROMIUM_ARGS="--no-sandbox"`.

## 7. Two checkpoints with the user
1. **The body and the default outfit** (shirt, trousers, shoes), shown next to the reference picture.
   Do not draw the other layers before the user approves the look.
2. **All layers:** the contact sheet and the card in two views.

## 8. Where the figure goes
- **A character you do not own** (anything from a TV show, film or game): private only. Keep it in
  `local/figures/<name>/` (git-ignored) and tell the user to copy it to `config/www/layercast/<name>/`
  and set the card option `figure_url: /local/layercast/<name>`. Never add it to the repository,
  its tests, screenshots or README.
- **An original figure** the user wants to ship: put it in
  `custom_components/layercast/www/figures/<name>/`, add it to `FIGURES` in
  `custom_components/layercast/www/layercast-card.js`, and the existing tests check it. Run the
  repository checks (`ruff`, `pytest`, `node --test tests/card.test.mjs`).

## Troubleshooting
| Symptom | Change |
|---|---|
| a jacket is too small for the sweater under it | grow `r`, `m`, `lift` or `t` of the jacket; the generator prints which pair. A margin that is exactly 0 means the two cuff lines coincide (raise `t`); one near 0.5 close to the neck means the shoulder angle (raise `lift`) |
| skin between sleeve and body | `ARM_R`, or the sleeve `r`; check `SHOULDER` is inside the torso edge |
| the hand is not at the cuff | `t` of the sleeve (0 shoulder, 1 wrist), `HAND_AT` |
| trousers do not reach the shoes | `LEG_BOTTOM`, `TROUSERS`, `SHOE_TOP` |
| shoes overlap | `SHOE_OUT`, `LEG_X`, `LEG_W` |
| hat covers the eyes | `HAT_BAND_Y` up, or `EYE_Y` down |
| the head looks wrong next to the picture | `HEAD_*` and the shapes in `head()`; the eyes and the muzzle matter most |
| the umbrella is cut off at the bottom | `UMBRELLA_LEN` smaller |
| a layer looks right alone, wrong with others | its `z` in `Z`, or its size against the layer under it |
