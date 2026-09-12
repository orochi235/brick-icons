#!/usr/bin/env python
"""What a printed part's decoration looks like BEFORE `significant_groups`.

A part that draws no decal gives the wall nothing to look at -- the failure is
an empty file. This tiles every group `decal_groups` bound, one cell each, so
the shape of the failure is visible: one clean panel, a print cut into a
handful of facet-sized pieces, or a mosaic of shards.

    scripts/show-decal-shards.py 3960pb0 --out out/shards

`significant_groups` is disarmed in-process rather than reimplemented, so the
cells are the same groups the renderer decided about.
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from brick_icons import unwrap  # noqa: E402
from brick_icons.hlr import part_geometry  # noqa: E402


def all_panels(tri, colors, analytic):
    """Every bound group as a panel, cap and sliver rules switched off."""
    keep = unwrap.significant_groups
    unwrap.significant_groups = lambda groups: groups
    try:
        return unwrap.decal_panels(tri, colors, analytic)
    finally:
        unwrap.significant_groups = keep


def sheet(panels, px=900, ldraw_dir="vendor/ldraw", bg="white"):
    """The panels on one canvas at one LDU scale, in a square-ish grid."""
    sized = [(ext, regions, face, *unwrap._extent_size(ext))
             for ext, regions, face in panels]
    if not sized:
        return None
    cols = max(1, math.ceil(math.sqrt(len(sized))))
    rows = math.ceil(len(sized) / cols)
    cell_w = max(p[3] for p in sized)
    cell_h = max(p[4] for p in sized)
    gutter = unwrap.SHEET_GUTTER * max(cell_w, cell_h)
    sheet_w = cols * cell_w + (cols + 1) * gutter
    sheet_h = rows * cell_h + (rows + 1) * gutter
    s = px / max(sheet_w, sheet_h, 1e-9)
    w, h = sheet_w * s, sheet_h * s

    body = [f'<rect width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>']
    for i, (ext, regions, face, pw, ph) in enumerate(sized):
        col, row = i % cols, i // cols
        dx = (gutter + col * (cell_w + gutter) + (cell_w - pw) / 2) * s
        dy = (gutter + row * (cell_h + gutter) + (cell_h - ph) / 2) * s
        paths = unwrap._panel_paths(ext, regions, s, ldraw_dir, face)
        body.append(f'<g transform="translate({dx:.2f} {dy:.2f})">'
                    + "".join(paths) + "</g>")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}">' + "".join(body) + "</svg>")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--out", default="out/shards")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(args.parts, 1):
        tri, colors, analytic = part_geometry(part, args.ldraw)
        panels = all_panels(tri, colors, analytic)
        svg = sheet(panels, px=args.px, ldraw_dir=args.ldraw)
        if svg is None:
            print(f"{i}/{len(args.parts)}  {part:14s} nothing bound", flush=True)
            continue
        path = out / f"{part}.shards.svg"
        path.write_text(svg)
        png = path.with_suffix(".png")
        subprocess.run(["resvg", str(path), str(png)], check=True)
        print(f"{i}/{len(args.parts)}  {part:14s} {len(panels)} groups -> {png}",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
