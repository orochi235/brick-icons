#!/usr/bin/env python3
"""Overlay a naive render on its occt counterpart: where do they differ ON PAGE?

    scripts/engine-overlay.py 4070 3941 --out /tmp/ovl.png

Red = naive only, blue = occt only, black = both. The share of shared ink is
the parity number that matters: two engines can emit completely different op
LISTS -- the same stroke cut into a different number of visible spans -- and
still put identical ink on the page, so an op-level or SVG-text diff reports
a disagreement the reader cannot see. This finds the ones they can.

Pair it with `engine-parity.py`, which answers the opposite question: what in
the TEXT differs, and how much of that is presentation.
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DEFAULT_PARTS = ["3070b", "3020", "3005", "3001", "4070", "3941"]
ARGS = ["--format", "svg", "--shading", "outline"]
W = 300
ROOT = Path("/Users/mike/src/brick-icons")
PY_ = ROOT / ".venv/bin/python"


def render(part, engine, work):
    out = work / f"{part}-{engine}"
    out.mkdir(parents=True, exist_ok=True)
    p = subprocess.run([str(PY_), "-m", "brick_icons.cli", part, *ARGS,
                        "--engine", engine, "--out", str(out)],
                       capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if not svgs:
        return None, None
    png = out / "r.png"
    subprocess.run(["resvg", "--width", str(W), str(svgs[0]), str(png)],
                   capture_output=True, check=True)
    vb = [l for l in svgs[0].read_text().splitlines() if "viewBox" in l]
    return png, (vb[0].split('viewBox="')[1].split('"')[0] if vb else "?")


def ink(png):
    """Ink intensity 0..1 on white ground."""
    im = Image.open(png).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return 1.0 - np.asarray(bg.convert("L"), np.float64) / 255.0


def panel(arr_rgb, label, font):
    h, w = arr_rgb.shape[:2]
    im = Image.new("RGB", (w, h + 18), (255, 255, 255))
    im.paste(Image.fromarray(arr_rgb.astype(np.uint8), "RGB"), (0, 0))
    ImageDraw.Draw(im).text((3, h + 4), label, fill=(20, 20, 20), font=font)
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="*", default=None)
    ap.add_argument("--angle", default=None)
    ap.add_argument("--out", type=Path, default=Path("/tmp/engine-overlay.png"))
    ns = ap.parse_args()
    parts = ns.parts or DEFAULT_PARTS
    if ns.angle:
        ARGS.extend(["--angle", ns.angle])
    work = Path(tempfile.mkdtemp(prefix="ovl-"))
    font = ImageFont.load_default(size=11)
    title_font = ImageFont.load_default(size=15)
    rows = []
    for n, part in enumerate(parts, 1):
        pn, vn = render(part, "naive", work)
        po, vo = render(part, "occt", work)
        if pn is None or po is None:
            print(f"{part}: render failed"); continue
        a, b = ink(pn), ink(po)
        if a.shape != b.shape:
            print(f"{part}: size mismatch {a.shape} vs {b.shape}"); continue
        h, w = a.shape
        mono_n = np.repeat((255 * (1 - a))[:, :, None], 3, 2)
        mono_o = np.repeat((255 * (1 - b))[:, :, None], 3, 2)
        over = np.stack([255 * (1 - b), 255 * (1 - np.maximum(a, b)),
                         255 * (1 - a)], axis=2)
        only_n = float(np.sum((a > 0.5) & (b <= 0.5)))
        only_o = float(np.sum((b > 0.5) & (a <= 0.5)))
        both = float(np.sum((a > 0.5) & (b > 0.5)))
        tot = both + only_n + only_o or 1.0
        cap = (f"{part}   shared {100*both/tot:4.1f}%   "
               f"naive-only {100*only_n/tot:4.1f}%   occt-only {100*only_o/tot:4.1f}%")
        strip = Image.new("RGB", (w * 3 + 24, h + 18 + 20), (255, 255, 255))
        for i, (arr, lab) in enumerate([(mono_n, "naive"), (mono_o, "occt"),
                                        (over, "overlay")]):
            strip.paste(panel(arr, lab, font), (i * (w + 12), 20))
        ImageDraw.Draw(strip).text((3, 3), cap, fill=(10, 10, 10), font=font)
        rows.append(strip)
        print(f"{part}: viewBox {vn} / {vo}  shared {100*both/tot:.1f}%  [{n}/{len(parts)}]")

    if not rows:
        return 1
    pad, top = 10, 34
    sheet_w = max(r.width for r in rows) + pad * 2
    sheet_h = sum(r.height for r in rows) + pad * (len(rows) + 1) + top
    sheet = Image.new("RGB", (sheet_w, sheet_h), (250, 250, 250))
    d = ImageDraw.Draw(sheet)
    pose = ns.angle or "iso"
    d.text((pad, 8), f"engine overlay - red = naive only, blue = occt only, "
                     f"black = both   (--shading outline, {pose})",
           fill=(10, 10, 10), font=title_font)
    y = top
    for r in rows:
        sheet.paste(r, (pad, y)); y += r.height + pad
    out = ns.out
    sheet.save(out)
    print(f"\nwrote {out}  {sheet.width}x{sheet.height}")
    return 0


sys.exit(main())
