#!/usr/bin/env python3
"""Which counterbore refits the pinch guard removes, over a corpus.

    .venv/bin/python scripts/measure-pinch-guard.py --list parts.txt \
        --out out/pinch-guard.jsonl --workers 6

`_snap_rim_crossings` pass 2 refits a separator through the bore's endpoints,
and PINCH_ON_F_TOL demands those endpoints lie on the opening circle. This
draws each part once (naive) and runs the pass twice on the same ops -- guard
off, guard on -- so the difference is the guard's alone. One row per part:
the refits kept and the refits dropped, each with how far the bore's ends sat
from the opening in its unit space (`ends`), so the threshold can be read
against the corpus rather than against the one part that motivated it.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr  # noqa: E402

LIB = ROOT / "vendor" / "ldraw"


def _radius(op):
    return (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0


def _point(op, t):
    th = math.radians(t)
    return np.array([op[1] + math.cos(th) * op[3] + math.sin(th) * op[5],
                     op[2] + math.cos(th) * op[4] + math.sin(th) * op[6]])


def _ends_on_F(segs, M, B):
    """The bore's endpoint radii in the opening's unit space (1.0 = on it)."""
    rM, cM = _radius(M), np.array(M[1:3])
    full = [op for op in segs if op[0] == "arc" and abs(op[8] - op[7]) >= 359.9
            and abs(_radius(op) - rM) <= 0.01 * rM
            and 1e-6 < np.hypot(*(cM - np.array(op[1:3]))) < rM]
    if not full:
        return None
    F = min(full, key=lambda op: np.hypot(*(cM - np.array(op[1:3]))))
    Minv = np.linalg.inv(np.array([[F[3], F[5]], [F[4], F[6]]], float))
    cF = np.array(F[1:3])
    return [round(float(np.hypot(*(Minv @ (_point(B, t) - cF)))), 3)
            for t in (B[7], B[8])]


def one(part):
    got = {}
    orig = hlr._snap_rim_crossings

    def spy(segs, **kw):
        tol = hlr.PINCH_ON_F_TOL
        hlr.PINCH_ON_F_TOL = math.inf
        try:
            _, before = orig(segs, **kw)
        finally:
            hlr.PINCH_ON_F_TOL = tol
        out, after = orig(segs, **kw)
        got["segs"], got["before"], got["after"] = segs, before, after
        return out, after

    hlr._snap_rim_crossings = spy
    try:
        hlr.visible_segments(part, LIB, render_px=512, engine="naive")
    except Exception as e:
        return {"part": part, "error": f"{type(e).__name__}: {e}"}
    finally:
        hlr._snap_rim_crossings = orig
    if not got:
        return {"part": part, "kept": [], "dropped": []}
    kept_new = {id(n) for _o, n, _b in got["after"]}
    rows = {"kept": [], "dropped": []}
    for old, new, bore in got["before"]:
        # the same refit recomputed lands on the same floats
        same = any(n == new for _o, n, _b in got["after"])
        rows["kept" if same else "dropped"].append({
            "r_old": round(_radius(old), 3), "r_new": round(_radius(new), 3),
            "sweep_old": round(abs(old[8] - old[7]), 1),
            "sweep_new": round(abs(new[8] - new[7]), 1),
            "sweep_bore": round(abs(bore[8] - bore[7]), 1),
            "ends": _ends_on_F(got["segs"], old, bore)})
    return {"part": part, **rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    parts = [s for ln in Path(a.list).read_text().splitlines()
             if (s := ln.split("#")[0].strip())]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    n_kept = n_dropped = 0
    with Path(a.out).open("w") as fh, ProcessPoolExecutor(a.workers) as ex:
        for i, row in enumerate(ex.map(one, parts), 1):
            fh.write(json.dumps(row) + "\n")
            k, d = len(row.get("kept", ())), len(row.get("dropped", ()))
            n_kept += k
            n_dropped += d
            tag = row.get("error", f"kept {k} dropped {d}")
            print(f"[{i}/{len(parts)}] {row['part']}: {tag}", flush=True)
    print(f"refits kept {n_kept}, dropped {n_dropped}")


if __name__ == "__main__":
    main()
