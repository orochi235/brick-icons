#!/usr/bin/env python3
"""How far a counterbore separator's refit moves its RADIUS, over a corpus.

    .venv/bin/python scripts/measure-refit-radius.py \
        --list out/census/ab-drawn-parts.txt --sample 600 --out out/refit-radius.json

`_snap_rim_crossings` pass 2 refits an authored separator onto a circumcircle
through the bore's endpoints and the separator's midpoint. `SEP_REFIT_MAX_GROWTH`
caps how far the SWEEP may grow and nothing caps the radius, so a refit is free
to land a ring at a radius the part never authored -- 6589 draws one at r=12.80
where the .dat authors 9, 10, 12 and 16.

Reports two things per refit: the ratio new/authored radius, and how near the
refit radius lands to a radius the part actually DECLARES on that axis -- the
other arcs sharing its center. Coaxial arcs project with the same foreshortening,
so their projected radii are in the authored ratio and the comparison holds in
canvas units. A refit onto a declared radius is a seam moving to meet geometry
that exists; one between them is a ring the part never had.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr  # noqa: E402


def _radius(op) -> float:
    return (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0


def _deviation(old, new) -> float:
    """Max radial distance from the authored curve to the refit one, op units.

    The same quantity `_refit_candidates` measures to size a seam's snap
    tolerance -- how far the refit moved the curve it claims to be a snap of.
    """
    ts = np.radians(np.linspace(old[7], old[8], 33))
    px = old[1] + np.cos(ts) * old[3] + np.sin(ts) * old[5]
    py = old[2] + np.cos(ts) * old[4] + np.sin(ts) * old[6]
    try:
        Mninv = np.linalg.inv(np.array([[new[3], new[5]], [new[4], new[6]]], float))
    except np.linalg.LinAlgError:
        return float("inf")
    mu = Mninv @ (np.stack([px, py], 0) - np.array(new[1:3], float).reshape(2, 1))
    ru = np.hypot(mu[0], mu[1])
    pr = np.hypot(px - new[1], py - new[2])
    return float(np.max(np.abs(ru - 1.0) * pr / np.maximum(ru, 1e-9)))


def _nearest_declared(new, segs, center_tol: float = 0.02) -> float | None:
    """Relative distance from the refit radius to the nearest coaxial arc's.

    Coaxial is judged against the refit's own radius, so the tolerance is a
    fraction of the ring rather than an absolute canvas distance.
    """
    r_new = _radius(new)
    if r_new <= 0:
        return None
    cx, cy = new[1], new[2]
    near = [_radius(op) for op in segs
            if op[0] == "arc"
            and math.hypot(op[1] - cx, op[2] - cy) <= center_tol * r_new]
    near = [r for r in near if r > 0 and abs(r - r_new) > 1e-9]
    return round(min(abs(r - r_new) / r_new for r in near), 4) if near else None


def measure(part: str, ldraw_dir: str, render_px: int) -> dict:
    """Every refit pass 2 performs on this part, as ratios against the authored arc."""
    box: dict = {}
    orig = hlr._snap_rim_crossings

    def spy(segs, **kw):
        out, refits = orig(segs, **kw)
        box.setdefault("refits", []).extend(refits)
        box.setdefault("segs", []).extend(segs)
        return out, refits

    hlr._snap_rim_crossings = spy
    try:
        hlr.visible_segments(part, ldraw_dir, render_px=render_px, engine="naive")
    finally:
        hlr._snap_rim_crossings = orig

    segs = box.get("segs", [])
    rows = []
    for old, new, bore in box.get("refits", []):
        r_old, r_new = _radius(old), _radius(new)
        dev = _deviation(old, new)
        rows.append({
            "dev": round(dev, 3),
            "dev_rel": round(dev / r_old, 4) if r_old else None,
            "declared": _nearest_declared(new, segs),
            "r_old": round(r_old, 3), "r_new": round(r_new, 3),
            "r_ratio": round(r_new / r_old, 4) if r_old else None,
            "sweep_old": round(abs(old[8] - old[7]), 2),
            "sweep_new": round(abs(new[8] - new[7]), 2),
            "growth": round(abs(new[8] - new[7]) / abs(old[8] - old[7]), 3)
            if abs(old[8] - old[7]) > 1e-9 else None,
            "r_bore": round(_radius(bore), 3),
        })
    return {"part": part, "refits": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part_ids", nargs="*")
    ap.add_argument("--list", type=Path, help="part ids, one per line")
    ap.add_argument("--sample", type=int, help="random subset of --list")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--ldraw-dir", default=str(ROOT / "vendor" / "ldraw"))
    ap.add_argument("--render-px", type=int, default=512)
    ap.add_argument("--parts", help="comma-separated ids, for onto --each")
    ap.add_argument("--jsonl", type=Path,
                    help="append one part per line as it finishes, so a killed "
                         "run resumes instead of restarting")
    ap.add_argument("--skip-done", action="store_true",
                    help="with --jsonl, skip parts already recorded there")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    parts = [p for p in (args.parts or "").split(",") if p]
    parts += list(args.part_ids)
    if args.list:
        parts += [ln.split()[0] for ln in args.list.read_text().split("\n")
                  if ln.strip() and not ln.startswith("#")]
    if args.sample and len(parts) > args.sample:
        random.Random(args.seed).shuffle(parts)
        parts = parts[:args.sample]

    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.jsonl and args.skip_done and args.jsonl.exists():
        done = {json.loads(ln)["part"] for ln in
                args.jsonl.read_text().split("\n") if ln.strip()}
        parts = [p for p in parts if p not in done]

    rows, ratios, declared, devs = [], [], [], []
    print(f"onto: plan 0/{len(parts)} refit-radius", flush=True)
    for n, part in enumerate(parts, 1):
        try:
            row = measure(part, args.ldraw_dir, args.render_px)
        except BaseException as exc:      # a part must not end the run
            row = {"part": part, "error": type(exc).__name__}
        rows.append(row)
        ratios.extend(r["r_ratio"] for r in row.get("refits", [])
                      if r["r_ratio"] is not None)
        declared.extend(r["declared"] for r in row.get("refits", [])
                        if r.get("declared") is not None)
        devs.extend((r["dev_rel"], row["part"]) for r in row.get("refits", [])
                    if r.get("dev_rel") is not None)
        if args.jsonl:
            with args.jsonl.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
        print(f"{n}/{len(parts)} {part:<16} refits {len(row.get('refits', [])):2d}"
              f"  errors {'yes' if 'error' in row else 'no'}", flush=True)
        print(f"onto: progress {n}/{len(parts)} refit-radius", flush=True)

    if args.out:
        args.out.write_text(json.dumps(rows, indent=1))
    print(f"\nparts {len(rows)}, with a refit "
          f"{sum(1 for r in rows if r.get('refits')):d}, refits {len(ratios)}")
    if ratios:
        rs = sorted(ratios)
        def pct(p):
            return rs[min(len(rs) - 1, int(len(rs) * p))]
        print(f"  r_new/r_old  min {rs[0]:6.3f}  p05 {pct(.05):6.3f}  "
              f"p50 {pct(.50):6.3f}  p95 {pct(.95):6.3f}  max {rs[-1]:6.3f}")
        print(f"  below 0.95x: {sum(1 for r in rs if r < 0.95)}   "
              f"above 1.05x: {sum(1 for r in rs if r > 1.05)}")
    if devs:
        vs = sorted(devs)
        print("  dev/r_old, the refit's departure from the curve it snaps:")
        for v, part in vs:
            print(f"    {v:7.4f}  {part}")
    if declared:
        ds = sorted(declared)
        def dpct(p):
            return ds[min(len(ds) - 1, int(len(ds) * p))]
        print(f"  gap to nearest declared coaxial radius, relative:")
        print(f"    min {ds[0]:6.4f}  p50 {dpct(.50):6.4f}  p90 {dpct(.90):6.4f}"
              f"  max {ds[-1]:6.4f}")
        for t in (0.005, 0.01, 0.02, 0.05):
            print(f"    within {t:5.3f}: {sum(1 for d in ds if d <= t):4d}"
                  f" of {len(ds)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
