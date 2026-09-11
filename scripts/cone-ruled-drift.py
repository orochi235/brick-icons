#!/usr/bin/env python3
"""What ruling the oblique cones changes, and what it leaves alone.

    .venv/bin/python scripts/cone-ruled-drift.py --n 120 --out out/cone-drift.jsonl
    .venv/bin/python scripts/cone-ruled-drift.py --parts 35485 2526

Draws each part twice in one process -- once with `oblique_cone` disarmed, so
`occt_faces` returns [] for a skew or elliptical con the way it did before --
and compares the drawn segments. A part with no such cone must come back
segment for segment; anything else is the finding.

`--affected` samples only from parts that hold one, `--control` only from
parts that hold a cone and no dropped one. Reports a line per part as it goes.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import arcfit, config, db, hlr, occt  # noqa: E402


def _refuse(*a, **k):
    raise RuntimeError("disarmed")


def segs_of(out, right, up, px):
    res = occt.visible_segments(out, right, up, px)
    return sorted(tuple(round(v, 4) if isinstance(v, (int, float)) else str(v)
                        for v in seg) for seg in res.segs)


def dropped_cones(out) -> int:
    """Cones that build nothing with `oblique_cone` disarmed -- the parts this
    change is for."""
    real, occt.oblique_cone = occt.oblique_cone, _refuse
    try:
        return sum(1 for p in out["analytic"]
                   if p.kind == "con" and not occt.occt_faces(p))
    finally:
        occt.oblique_cone = real


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--parts", nargs="+")
    ap.add_argument("--affected", action="store_true",
                    help="only parts holding a cone this change builds")
    ap.add_argument("--control", action="store_true",
                    help="only parts holding a cone it does not touch")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--out", default="out/cone-ruled-drift.jsonl")
    args = ap.parse_args()

    if args.parts:
        sample = list(args.parts)
    else:
        conn = sqlite3.connect(ROOT / db.DEFAULT_PATH)
        sample = [r[0] for r in conn.execute(
            "SELECT part_id FROM part_features WHERE feature='cone' "
            "ORDER BY part_id")]
        random.seed(args.seed)
        random.shuffle(sample)

    ldraw = config.load_config().ldraw_dir
    right, up, _fwd = hlr.view_basis(30.0, 45.0)
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    real = occt.oblique_cone
    changed = same = failed = skipped = 0
    kept = 0
    with outp.open("w") as fh:
        for part in sample:
            if kept >= args.n and not args.parts:
                break
            t0 = time.time()
            row = {"part": part}
            try:
                out = occt.flatten_part(part, ldraw)
                out["fit_arcs"], out["2"] = arcfit.fit_edge_arcs(out["2"], out["5"])
                n = dropped_cones(out)
                if (args.affected and not n) or (args.control and n):
                    skipped += 1
                    continue
                occt.oblique_cone = _refuse
                a = segs_of(out, right, up, args.px)
                occt.oblique_cone = real
                b = segs_of(out, right, up, args.px)
                moved = a != b
                row.update(cones=n, before=len(a), after=len(b),
                           changed=bool(moved), secs=round(time.time() - t0, 2))
                changed += bool(moved)
                same += not moved
            except Exception as e:
                occt.oblique_cone = real
                row.update(error=type(e).__name__, detail=str(e)[:200])
                failed += 1
            kept += 1
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            mark = "CHANGED" if row.get("changed") else (
                "error" if "error" in row else "same")
            print(f"{kept}/{args.n} {part}: {mark} cones={row.get('cones','-')} "
                  f"{row.get('before','-')}->{row.get('after','-')} segs "
                  f"[{row.get('secs','-')}s]", flush=True)
    print(f"\nkept {kept} (skipped {skipped}): changed {changed}, "
          f"unchanged {same}, errors {failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
