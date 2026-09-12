#!/usr/bin/env python
"""What is drawn inside one pixel box, and which rule emitted it.

`probe-drawn-classes.py` answers "does suppressing this rule move the ink";
this answers "what IS that line" -- the drawn ops whose canvas geometry falls
inside a box, each with its tag and the primitive kind behind it. The box is
in the coordinates of the SVG the CLI writes at this width.

Usage: probe-segs-in-box.py 24434 --box X Y W H [--engine naive]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, hlr  # noqa: E402


def op_points(op) -> np.ndarray:
    """Canvas points an op passes through, enough to test a box against."""
    if op[0] == "line":
        return np.array([[op[1], op[2]], [op[3], op[4]]], float)
    if op[0] == "arc":
        # ("arc", cx, cy, ux, uy, vx, vy, d0, d1, tag)
        cx, cy, ux, uy, vx, vy, d0, d1 = op[1:9]
        th = np.radians(np.linspace(d0, d1, 33))
        return np.stack([cx + ux * np.cos(th) + vx * np.sin(th),
                         cy + uy * np.cos(th) + vy * np.sin(th)], 1)
    return np.empty((0, 2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--box", nargs=4, type=float, required=True,
                    metavar=("X", "Y", "W", "H"))
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--mark", type=int, nargs="*", default=None,
                    help="write an SVG with these op indices in red")
    ap.add_argument("--svg", default=None)
    args = ap.parse_args()

    cfg = cli._config_from_args(cli.build_parser().parse_args(
        [args.part, "--engine", args.engine, "--render-px", str(args.width)]))
    res = hlr.visible_segments(args.part, cfg.ldraw_dir, lat=30.0, long=45.0,
                               render_px=args.width, engine=args.engine)
    segs = res.segs
    # The CLI fits the drawing to the canvas after culling; do the same so the
    # box matches what a viewer measured off the written SVG.
    bbox = hlr._ops_bbox(segs)
    f, ox, oy = hlr.fit_affine(bbox, args.width, args.width)
    placed = hlr.fit_segments(segs, bbox, args.width, args.width)

    x, y, w, h = args.box
    print(f"{len(placed)} ops drawn; box {x},{y} {w}x{h}")
    hits = 0
    for i, op in enumerate(placed):
        pts = op_points(op)
        if len(pts) == 0:
            continue
        inside = ((pts[:, 0] >= x) & (pts[:, 0] <= x + w)
                  & (pts[:, 1] >= y) & (pts[:, 1] <= y + h))
        if not inside.any():
            continue
        hits += 1
        frac = inside.mean()
        p0, p1 = pts[0], pts[-1]
        print(f"  [{i}] {op[0]:<4} tag={op[-1]:<5} {frac:5.0%} in box  "
              f"({p0[0]:7.1f},{p0[1]:7.1f}) -> ({p1[0]:7.1f},{p1[1]:7.1f})")
    print(f"{hits} ops touch the box")
    if args.mark is not None:
        dst = Path(args.svg or f"{args.part}-marked.svg")
        marked = set(args.mark)
        body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{args.width}"'
                f' height="{args.width}" viewBox="0 0 {args.width} {args.width}">',
                '<rect width="100%" height="100%" fill="white"/>']
        for i, op in enumerate(placed):
            pts = op_points(op)
            if len(pts) < 2:
                continue
            d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
            hot = i in marked
            body.append(f'<path d="{d}" fill="none" stroke='
                        f'"{"#d81b1b" if hot else "#c8c8c8"}" '
                        f'stroke-width="{4 if hot else 2}"/>')
        body.append("</svg>")
        dst.write_text("\n".join(body))
        print(f"marked {sorted(marked)} -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
