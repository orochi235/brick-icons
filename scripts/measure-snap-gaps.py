#!/usr/bin/env python3
"""How far an arc's drawn end sits from the junction it grazes, per engine.

    .venv/bin/python scripts/measure-snap-gaps.py --list out/census/ab-drawn-parts.txt \
        --sample 400 --engine occt --out out/snap-gaps-occt.json

`hlr._snap_rim_crossings` pass 1 exists because naive's occlusion is sampled:
`visible_subops` stops up to a sample short of the true graze, so an arc end
lands beside the stroke it should touch. occt does real hidden-line removal, so
the question is whether it leaves a gap at all. This runs the pass over each
engine's pre-snap ops and reports what it would move, in degrees and in output
px at `--out-width` -- naive's ops are canvas px at `render_px` and occt's are
projected LDU, so the fit scale is applied before anything is compared.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr  # noqa: E402


def _pre_snap_ops(part: str, ldraw_dir: str, engine: str, render_px: int):
    """The ops as they reach `_snap_rim_crossings` (naive) or would (occt)."""
    box: dict = {}
    if engine == "naive":
        orig = hlr._snap_rim_crossings

        def spy(segs, **kw):
            box["segs"] = list(segs)
            return orig(segs, **kw)

        hlr._snap_rim_crossings = spy
    else:
        orig = hlr.dedupe_segments

        def spy(segs, **kw):
            got = orig(segs, **kw)
            box["segs"] = list(got)
            return got

        hlr.dedupe_segments = spy
    try:
        res = hlr.visible_segments(part, ldraw_dir, render_px=render_px,
                                   engine=engine)
    finally:
        if engine == "naive":
            hlr._snap_rim_crossings = orig
        else:
            hlr.dedupe_segments = orig
    return box.get("segs", []), res


def _radius(op) -> float:
    return (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0


def measure(part: str, ldraw_dir: str, engine: str, render_px: int,
            out_width: int, margin: int) -> dict:
    segs, res = _pre_snap_ops(part, ldraw_dir, engine, render_px)
    f = hlr.fit_affine(res.bbox, out_width, out_width, margin, 1.0)[0]
    # vertex_tol is op units: canvas px on naive, LDU on occt (cf. dedupe's eps)
    vtol = 0.25 if engine == "naive" else 0.25 / (res.s or 1.0)
    snapped, refits = hlr._snap_rim_crossings(segs, vertex_tol=vtol)
    # pass 2 replaces whole ops; revert those so the moves are pass 1's alone
    reverted = {id(new): old for old, new, _ in refits}
    pass1 = [reverted.get(id(op), op) for op in snapped]
    moves = []
    for before, after in zip(segs, pass1):
        if before[0] != "arc" or (before[7], before[8]) == (after[7], after[8]):
            continue
        r_px = _radius(before) * f
        for i in (7, 8):
            d = abs(after[i] - before[i])
            if d > 1e-12:
                moves.append([d, math.radians(d) * r_px])
    return {
        "part": part, "engine": engine, "ops": len(segs),
        "arcs": sum(1 for op in segs if op[0] == "arc"),
        "partial": sum(1 for op in segs
                       if op[0] == "arc" and abs(op[8] - op[7]) < 359.9),
        "refits": len(refits), "moves": moves,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=Path, help="part ids, one per line")
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--sample", type=int, help="random subset of --list")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--ldraw-dir", default="vendor/ldraw")
    ap.add_argument("--render-px", type=int, default=2048)
    ap.add_argument("--out-width", type=int, default=512)
    ap.add_argument("--margin", type=int, default=6)
    ap.add_argument("--visible-px", type=float, default=0.5,
                    help="a move this big or bigger is one a reader can see")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    parts = list(args.parts)
    if args.list:
        parts += [ln.split("#")[0].strip() for ln in args.list.read_text().splitlines()]
    parts = [p for p in parts if p]
    if args.sample and args.sample < len(parts):
        parts = random.Random(args.seed).sample(parts, args.sample)
    if not parts:
        ap.error("no parts")

    rows, failed = [], 0
    for i, part in enumerate(parts, 1):
        t = time.perf_counter()
        try:
            row = measure(part, args.ldraw_dir, args.engine, args.render_px,
                          args.out_width, args.margin)
        except BaseException as e:                     # a crash is a result too
            failed += 1
            print(f"{i}/{len(parts)} {part:<12} FAILED {type(e).__name__}: {e}",
                  flush=True)
            continue
        big = [m for m in row["moves"] if m[1] >= args.visible_px]
        row["visible"] = len(big)
        rows.append(row)
        worst = max((m[1] for m in row["moves"]), default=0.0)
        print(f"{i}/{len(parts)} {part:<12} arcs {row['arcs']:4d}  "
              f"moved {len(row['moves']):4d}  >={args.visible_px}px "
              f"{len(big):4d}  worst {worst:7.2f}px  refits {row['refits']:2d}  "
              f"{time.perf_counter() - t:5.1f}s", flush=True)

    seen = [r for r in rows if r["visible"]]
    allmv = [m[1] for r in rows for m in r["moves"]]
    print()
    print(f"{args.engine}: {len(rows)} parts measured, {failed} failed")
    print(f"  parts with a move >= {args.visible_px}px: {len(seen)} "
          f"({100.0 * len(seen) / max(len(rows), 1):5.1f}%)")
    print(f"  parts where pass 2 refits:                "
          f"{sum(1 for r in rows if r['refits'])}")
    if allmv:
        q = np.percentile(allmv, [50, 90, 99])
        print(f"  moves: {len(allmv):5d}   median {q[0]:6.3f}px   "
              f"p90 {q[1]:6.3f}px   p99 {q[2]:6.3f}px   max {max(allmv):7.3f}px")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(rows))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
