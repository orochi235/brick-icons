#!/usr/bin/env python3
"""Render a part list as a FACE-ONLY contact sheet: one flat color per fill
element, strokes dropped.

    python scripts/render-face-sheet.py --engine occt --list specimens.txt

The ordinary sheet draws a 2px stroke over every seam, which is exactly where
fill defects hide: a staircased boundary, a sliver on the wrong surface, a
fragment that should have merged into its neighbour. 4070's ledge seam was a
1.2px staircase that only showed because the stroke that would have covered
it was missing. This strips the strokes so no seam can hide behind one, and
cycles the fill colors so adjacent elements never share a tone.

It POST-PROCESSES the emitted SVG rather than adding a render mode, so what
you see is exactly what the renderer produced. `--debug-colors` is not this:
it recolors strokes and leaves the fills grey.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = "/System/Library/Fonts/Helvetica.ttc"

# cycled per fill element: adjacent surfaces must never land on one tone
PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#46f0f0",
           "#f032e6", "#bcf60c", "#008080", "#9a6324", "#800000", "#808000",
           "#000075", "#e6beff", "#aaffc3", "#ffd8b1"]


def faces_only(svg: str) -> str:
    """Drop stroke-only paths; give every remaining fill its own flat color."""
    n = 0

    def sub(m):
        nonlocal n
        attrs = m.group(1)
        fill = re.search(r'\bfill="([^"]*)"', attrs)
        if fill is None or fill.group(1) in ("none", "None"):
            return ""                       # a stroke op or the contour
        c = PALETTE[n % len(PALETTE)]
        n += 1
        out = re.sub(r'\bfill="[^"]*"', f'fill="{c}"', attrs)
        out = re.sub(r'\bstroke="[^"]*"', f'stroke="{c}"', out)
        return f"<path{out}>"

    return re.sub(r"<path([^>]*)>", sub, svg)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--list", default="specimens.txt")
    ap.add_argument("--out", default=None)
    ap.add_argument("--angle", default=None)
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--tile", default="6x")
    args = ap.parse_args(argv)

    out = Path(args.out or ROOT / "out" / f"face-sheet-{args.engine}")
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "brick_icons.cli", "--list", args.list,
           "--engine", args.engine, "--format", "svg", "--shading", "outline",
           "--shade-style", "flat3", "--part-label", "--out", str(out)]
    if args.angle:
        cmd += ["--angle", args.angle]
    # one line per part reaches the terminal as the CLI prints it
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        return 1

    pngs = []
    svgs = sorted(out.glob("*.svg"))
    for i, f in enumerate(svgs, 1):
        f.write_text(faces_only(f.read_text()))
        png = f.with_suffix(".png")
        subprocess.run(["resvg", "--background", "white", "--width",
                        str(args.width), str(f), str(png)], check=True)
        pngs.append(str(png))
        print(f"{i}/{len(svgs)} {f.stem}", flush=True)
    sheet = out / "face-sheet.png"
    # montage resolves no default font here, and fails even with no -label
    font = ["-font", FONT] if Path(FONT).exists() else []
    subprocess.run(["magick", "montage", *pngs, *font, "-tile", args.tile,
                    "-geometry", "+8+8", "-background", "white", str(sheet)],
                   check=True)
    print(f"face sheet: {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
