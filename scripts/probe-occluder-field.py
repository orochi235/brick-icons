#!/usr/bin/env python
"""Why an edge that should be hidden survives the depth test.

Rebuilds one part's naive scene, then for every drawn candidate reports how
much of it the occluders cover and by how far it missed -- so "the occluder is
absent" and "the occluder is there and the bias let it through" stop looking
alike. Prints the worst offenders: ops that are drawn while sitting behind
something.

Usage: probe-occluder-field.py 24434 [--engine naive]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, hlr, primitives  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--box", nargs=4, type=float, default=None,
                    metavar=("X", "Y", "W", "H"))
    args = ap.parse_args()

    cfg = cli._config_from_args(cli.build_parser().parse_args([args.part]))
    seen = []
    original = primitives.visible_subops

    def spy(op_specs, occluders, ray_origin, fwd, eps, n=200):
        kinds = {}
        for occ in occluders:
            kinds[type(occ).__name__] = kinds.get(type(occ).__name__, 0) + 1
        print(f"occluders: {kinds}  eps={eps:.4f}  specs={len(op_specs)}")
        for spec in op_specs:
            op, depth_fn = spec[0], spec[1]
            exclude = spec[2] if len(spec) > 2 else None
            proxy = spec[3] if len(spec) > 3 else None
            xs, ys, params = primitives._samples_for(op, n)
            if proxy is not None:
                xs, ys, sd = proxy(params)
                sd = np.asarray(sd, float)
            else:
                sd = np.asarray(depth_fn(params), float)
            O = ray_origin(xs, ys)
            field = np.full(xs.shape, np.inf)
            for occ in occluders:
                if occ is exclude:
                    continue
                field = np.minimum(field, occ.depth(O, fwd))
            behind = sd > field + eps
            vis = ~behind
            covered = np.isfinite(field)
            seen.append({
                "op": op, "n": len(xs),
                "behind": float(behind.mean()),
                "covered": float(covered.mean()),
                # how far in front of the nearest occluder the drawn samples
                # sit: negative means it is behind and should have been cut
                "clear": float(np.median(field[covered] - sd[covered]))
                if covered.any() else float("nan"),
                "x": float(np.median(xs)), "y": float(np.median(ys)),
                "excluded": exclude is not None,
                "vis": float(vis.mean()),
            })
        return original(op_specs, occluders, ray_origin, fwd, eps, n=n)

    primitives.visible_subops = spy
    try:
        hlr.visible_segments(args.part, cfg.ldraw_dir, lat=30.0, long=45.0,
                             render_px=args.width, engine="naive")
    finally:
        primitives.visible_subops = original

    drawn = [s for s in seen if s["vis"] > 0]
    if args.box:
        x, y, w, h = args.box
        drawn = [s for s in drawn
                 if x <= s["x"] <= x + w and y <= s["y"] <= y + h]
    drawn.sort(key=lambda s: s["covered"])
    print(f"\n{len(seen)} candidates; nearest-to-occluder first "
          f"(clear < 0 means it sits behind and was kept by the bias):")
    for s in drawn[:args.top]:
        print(f"  {s['op'][0]:<4} tag={s['op'][-1]:<5} "
              f"covered={s['covered']:5.0%} behind={s['behind']:5.0%} "
              f"vis={s['vis']:5.0%} clear={s['clear']:+8.3f} "
              f"at ({s['x']:7.1f},{s['y']:7.1f})"
              f"{'  [self-excluded]' if s['excluded'] else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
