#!/usr/bin/env python
"""Which primitive each drawn naive op came from, and how its depth compares
with the nearest occluder along its samples.

`probe-segs-in-box.py` names the op class in a pixel box; this names the
source: for every visible op, the analytic primitive (kind, world center,
axis, radius) or type-2 line behind it, with the share of its samples that
passed only because nothing nearer was found. Writes an SVG with each drawn
op numbered, so a line on a render can be read off by index.

Usage: probe-drawn-sources.py 24434 --svg out/probe/sources.svg [--width 900]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, hlr, primitives  # noqa: E402


def describe(prim) -> str:
    R, t = prim.R, prim.t
    ru = float(np.linalg.norm(R[:, 0]))
    A = R[:, 1]
    return (f"{prim.kind:<5} sect={prim.sector:5.1f} r={ru:5.1f} "
            f"C=({t[0]:6.1f},{t[1]:6.1f},{t[2]:6.1f}) "
            f"A=({A[0]:5.1f},{A[1]:5.1f},{A[2]:5.1f})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--svg", type=Path, required=True)
    args = ap.parse_args()

    captured = {}
    original = primitives.visible_subops

    def spy(op_specs, occluders, ray_origin, fwd, eps, n=200):
        captured["specs"] = list(op_specs)
        captured["occ"] = list(occluders)
        captured["ray"] = ray_origin
        captured["fwd"] = fwd
        captured["eps"] = eps
        return original(op_specs, occluders, ray_origin, fwd, eps, n=n)

    primitives.visible_subops = spy
    cfg = cli._config_from_args(cli.build_parser().parse_args(
        [args.part, "--engine", "naive", "--render-px", str(args.width)]))
    res = hlr.visible_segments(args.part, cfg.ldraw_dir, lat=30.0, long=45.0,
                               render_px=args.width, engine="naive")
    primitives.visible_subops = original

    proj = res.proj
    analytic = res.analytic
    key_src = {}
    for prim in analytic:
        for op, _d in prim.drawn_with_depth(proj):
            if op[0] == "arc":
                key_src.setdefault(tuple(round(x, 4) for x in op[1:7]), prim)

    index = primitives.OccluderIndex(captured["occ"], captured["fwd"])
    occ_names = []
    for o in captured["occ"]:
        owner = next((p for p in analytic if p.occluder() is o), None)
        occ_names.append(describe(owner) if owner is not None
                         else type(o).__name__)
    rows = []
    for spec in captured["specs"]:
        op, dfn = spec[0], spec[1]
        exclude = spec[2] if len(spec) > 2 else None
        if len(spec) > 3:
            continue
        xs, ys, params = primitives._samples_for(op, 64)
        sd = np.asarray(dfn(params), float)
        O = captured["ray"](xs, ys)
        field, which = index.nearest_hit(O, skip=[exclude] if exclude else ())
        vis = sd <= field + captured["eps"]
        if not vis.any():
            continue
        if op[0] == "arc":
            prim = key_src.get(tuple(round(x, 4) for x in op[1:7]))
            src = describe(prim) if prim is not None else "arc (fit/other)"
        else:
            src = f"line {op[-1]}"
        near = [occ_names[w] for w in which[vis] if w >= 0]
        top = max(set(near), key=near.count) if near else "-"
        runs = [np.stack([xs[i:j + 1], ys[i:j + 1]], 1)
                for i, j in primitives._runs(vis) if j > i]
        rows.append((op, runs, src, float(vis.mean()), top,
                     float(np.median(sd[vis])),
                     float(np.median(field[vis][np.isfinite(field[vis])]))
                     if np.isfinite(field[vis]).any() else float("inf")))

    W = args.width
    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" '
            f'height="{W}" viewBox="0 0 {W} {W}">',
            '<rect width="100%" height="100%" fill="white"/>']
    for i, (op, runs, src, frac, top, dz, fz) in enumerate(rows):
        print(f"[{i:3d}] {op[0]:<4} {op[-1]:<4} vis={frac:4.0%} "
              f"z={dz:7.2f} occ_z={fz:7.2f}  {src}\n        nearest: {top}")
        for pts in runs:
            d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts)
            body.append(f'<path d="{d}" fill="none" stroke="#333" '
                        f'stroke-width="1.5"/>')
        if not runs:
            continue
        mx, my = runs[0][len(runs[0]) // 2]
        body.append(f'<text x="{mx:.1f}" y="{my:.1f}" font-size="9" '
                    f'fill="#d81b1b">{i}</text>')
    body.append("</svg>")
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text("\n".join(body))
    print(f"wrote {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
