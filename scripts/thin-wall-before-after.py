"""Before/after sheet for the thin side-wall rule (shade.THIN_WALL_WEIGHTS),
both sides from THIS tree, with LDView's gray reference beside them.

    .venv/bin/python scripts/thin-wall-before-after.py --out out/thin-wall \\
        3811 2552p01 3020

A part is `<id>` or `<id>:<slot>` (default occt). `before` disarms the rule
in-process (THIN_WALL_WEIGHTS = 0); `fill` keeps the top-tone fill but
disarms the thinner crease (THIN_WALL_CREASE = False); `after` is the rule
as it stands. Each part gets a lightbox row, a 128 px icon row (shown 4x,
nearest-neighbor) and an 11x zoom on its front corner. A 64x profile down
each front wall goes to profiles.json: the unbroken dark run up from the
silhouette along one column, strokes included, in canvas px.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import brick_icons  # noqa: E402

assert Path(brick_icons.__file__).resolve().is_relative_to(ROOT), brick_icons.__file__

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import _sheet  # noqa: E402
from brick_icons import cli, db, render, shade  # noqa: E402

LB = 540                  # lightbox tile: 2x a ~270 CSS px tile
ZW, ZH, ZS = 44, 22, 11   # corner window in canvas px, and its zoom
PZ, PW, PH = 64, 6.0, 4.0 # profile zoom and window (canvas px)
DARK = 180                # darker than this reads as ink, not top (0xcc)
ICON = 128               # icon size, shown at ICON_ZOOM x
ICON_ZOOM = 4
VARIANTS = ("before", "fill", "after")
COLS = ("current (rule off)", "D as first built: top-tone fill",
        "D + crease at stud tier", "diff: current vs D + thin crease",
        "LDView gray -FOV=0.1")


def render_svg(part, slot, out_dir, variant):
    saved = (shade.THIN_WALL_WEIGHTS, shade.THIN_WALL_CREASE)
    if variant == "before":
        shade.THIN_WALL_WEIGHTS = 0
    elif variant == "fill":
        shade.THIN_WALL_CREASE = False
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        shade.THIN_WALL_WEIGHTS, shade.THIN_WALL_CREASE = saved
    return out_dir / f"{part}.svg"


def raster(svg, width, box=None):
    t = Path(svg).read_text()
    if box is not None:
        t = re.sub(r'viewBox="[^"]*"', 'viewBox="%g %g %g %g"' % tuple(box),
                   t, count=1)
    with tempfile.TemporaryDirectory() as td:
        s, p = Path(td) / "c.svg", Path(td) / "c.png"
        s.write_text(t)
        subprocess.run(["resvg", "--width", str(int(width)), "--background",
                        "white", str(s), str(p)], check=True, capture_output=True)
        return Image.open(p).convert("RGB")


def canvas_size(svg):
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', Path(svg).read_text())
    return float(m.group(1)), float(m.group(2))


def ink_bbox(im, thr=245):
    a = np.asarray(im.convert("L"))
    ys, xs = np.nonzero(a < thr)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def front_corner(svg):
    """(x, y) canvas px of the drawing's lowest point, and its bbox."""
    w, _h = canvas_size(svg)
    k = 8
    a = np.asarray(raster(svg, w * k).convert("L"))
    ys, xs = np.nonzero(a < 250)
    y = ys.max()
    x = xs[ys == y].mean()
    return (x / k, y / k), (xs.min() / k, ys.min() / k, xs.max() / k, y / k)


def profile(svg, x):
    """Runs down one column at 64x through the wall under canvas x."""
    w, h = canvas_size(svg)
    col = np.asarray(raster(svg, w * 8).convert("L"))[:, int(x * 8)]
    yb = np.nonzero(col < 250)[0].max() / 8.0
    box = (x - PW / 2, yb - PH + 0.5, PW, PH)
    a = np.asarray(raster(svg, PW * PZ, box).convert("L"), float)
    col = a[:, a.shape[1] // 2]
    runs, prev = [], None
    for i, v in enumerate(col):
        cls = "ink" if v < 40 else ("fill" if v < 250 else "bg")
        if cls != prev:
            runs.append([cls, i, i, []])
            prev = cls
        runs[-1][2] = i
        runs[-1][3].append(v)
    dark = np.nonzero(col < DARK)[0]
    run = 0
    for v in col[:dark.max() + 1][::-1]:
        if v >= DARK:
            break
        run += 1
    return {"x": round(x, 2), "dark_px": round(run / PZ, 3),
            "runs": [{"kind": c, "y0": round(box[1] + i0 / PZ, 3),
                      "h": round((i1 - i0 + 1) / PZ, 3),
                      "gray": round(float(np.median(vs)), 1)}
                     for c, i0, i1, vs in runs]}


def ldview_ref(part, png):
    args = cli._parse_args(db.canonical_argv(part, "reference-gray"))
    render.render_part(cli._config_from_args(args), part, png, timeout=300)
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return bg.convert("RGB")


def ref_crop(ref, bbox, box, width):
    """The part of the LDView image under canvas `box`, matched by bbox."""
    rx0, ry0, rx1, ry1 = ink_bbox(ref)
    sx0, sy0, sx1, sy1 = bbox
    k = (rx1 - rx0) / (sx1 - sx0)
    x0 = rx0 + (box[0] - sx0) * k
    y0 = ry1 - (sy1 - box[1]) * k
    crop = Image.new("RGB", (round(box[2] * k), round(box[3] * k)), "white")
    crop.paste(ref, (-round(x0), -round(y0)))
    return crop.resize((int(width), round(width * box[3] / box[2])), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/thin-wall")
    ap.add_argument("--title", default="Thin side walls along the silhouette "
                    "take the top tone (occt flat3), rule off vs on, same tree")
    ap.add_argument("--no-ref", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, profiles = [], {}
    n = len(a.parts)
    print(f"onto: plan 0/{n}", flush=True)
    for i, spec in enumerate(a.parts, 1):
        part, _, slot = spec.partition(":")
        slot = slot or "occt"
        svgs = {v: render_svg(part, slot, out / v, v)
                for v in VARIANTS}
        ref = None
        if not a.no_ref:
            try:
                ref = ldview_ref(part, out / "ref" / f"{part}.png")
            except Exception as e:  # noqa: BLE001
                print(f"  {part}: no LDView reference ({e})", flush=True)
        w, h = canvas_size(svgs["after"])
        (cx, cy), bbox = front_corner(svgs["after"])
        half = (bbox[2] - bbox[0]) / 2
        profiles[part] = {v: [profile(svgs[v], cx + s * 0.4 * half)
                              for s in (-1, 1)] for v in svgs}
        for box, width, tag in (((0, 0, w, h), LB, "lightbox"),
                                ((0, 0, w, h), ICON, f"icon {ICON}px, {ICON_ZOOM}x"),
                                ((cx - ZW / 2, cy - ZH + 3, ZW, ZH), ZW * ZS,
                                 f"front corner {ZS}x")):
            b, f1, af = (raster(svgs[v], width, box) for v in VARIANTS)
            d, comps, px = _sheet.diff_panel(b, af)
            r = ref_crop(ref, bbox, box, width) if ref is not None else \
                Image.new("RGB", af.size, "white")
            ims = [b, f1, af, d, r]
            if width == ICON:
                ims = [im.resize((im.width * ICON_ZOOM, im.height * ICON_ZOOM),
                                 Image.NEAREST) for im in ims]
            rows.append((f"{part}\n{tag}", (comps, px), ims))
        p = profiles[part]
        print(f"[{i}/{n}] {part} {slot}  dark px L/R before "
              f"{p['before'][0]['dark_px']:.3f}/{p['before'][1]['dark_px']:.3f}"
              f"  after {p['after'][0]['dark_px']:.3f}/{p['after'][1]['dark_px']:.3f}"
              f"  lightbox {rows[-3][1][0]} comp", flush=True)
        print(f"onto: progress {i}/{n}", flush=True)
    (out / "profiles.json").write_text(json.dumps(profiles, indent=1))

    font = ImageFont.load_default(size=16)
    small = ImageFont.load_default(size=13)
    W = max(im.width for _l, _n, ims in rows for im in ims)
    gutter, top, left = 12, 56, 150
    hs = [max(im.height for im in ims) for _l, _n, ims in rows]
    img = Image.new("RGB", (left + len(COLS) * (W + gutter) + gutter,
                            top + sum(hs) + gutter * len(rows)), "white")
    dr = ImageDraw.Draw(img)
    dr.text((gutter, 8), a.title, fill="black", font=font)
    for k, name in enumerate(COLS):
        dr.text((left + gutter + k * (W + gutter), 32), name, fill="black",
                font=font)
    y = top
    for (label, (comps, px), ims), hh in zip(rows, hs):
        dr.text((gutter, y + 4), label, fill="black", font=font)
        dr.text((gutter, y + 4 + 22 * (label.count("\n") + 1)),
                f"{comps} comp, {px} px",
                fill=_sheet.DIFF_COLOR if px else "gray", font=small)
        for k, im in enumerate(ims):
            img.paste(im, (left + gutter + k * (W + gutter), y))
        y += hh + gutter
    img.save(out / "sheet.png")
    print(out / "sheet.png", img.size, flush=True)


if __name__ == "__main__":
    main()
