#!/usr/bin/env python3
"""How many parts the crack repair changes, and by how much.

    .venv/bin/python scripts/crack-heal-drift.py --n 200 --out out/drift.jsonl

Draws each part twice in one process -- once with `heal_face_cracks` disarmed,
once at HEAD -- and compares the drawn segments. The repair is meant to touch
only faces the merge cracked, so a part with no crack must come back byte for
byte; anything else is the finding.

Reports one line per part as it goes.
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


def segs_of(out, right, up, px):
    """The drawn segments, canonically. A row is neither one fixed width nor
    all numbers -- an arc leads with its kind -- so they compare as rounded
    tuples rather than as an array."""
    res = occt.visible_segments(out, right, up, px)
    return sorted(tuple(round(v, 4) if isinstance(v, (int, float)) else str(v)
                        for v in seg) for seg in res.segs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--out", default="out/crack-heal-drift.jsonl")
    args = ap.parse_args()

    conn = sqlite3.connect(ROOT / db.DEFAULT_PATH)
    marks = ",".join("?" * len(db.OUT_OF_SCOPE_CATEGORIES))
    ids = [r[0] for r in conn.execute(
        f"SELECT id FROM parts WHERE obsolete=0 AND (category IS NULL OR "
        f"category NOT IN ({marks}))", db.OUT_OF_SCOPE_CATEGORIES)]
    random.seed(args.seed)
    sample = random.sample(ids, min(args.n, len(ids)))
    ldraw = config.load_config().ldraw_dir
    right, up, _fwd = hlr.view_basis(30.0, 45.0)

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    healed_n = changed = same = failed = 0
    real = occt.heal_face_cracks
    with outp.open("w") as fh:
        for i, part in enumerate(sample, 1):
            t0 = time.time()
            row = {"part": part}
            try:
                out = occt.flatten_part(part, ldraw)
                out["fit_arcs"], out["2"] = arcfit.fit_edge_arcs(out["2"], out["5"])
                occt.heal_face_cracks = lambda s: s
                a = segs_of(out, right, up, args.px)
                occt.heal_face_cracks = real
                b = segs_of(out, right, up, args.px)
                moved = a != b
                row.update(before=len(a), after=len(b), changed=bool(moved),
                           secs=round(time.time() - t0, 2))
                healed_n += bool(moved)
                changed += bool(moved)
                same += not moved
            except Exception as e:
                occt.heal_face_cracks = real
                row.update(error=type(e).__name__, detail=str(e)[:200])
                failed += 1
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            mark = "CHANGED" if row.get("changed") else (
                "error" if "error" in row else "same")
            print(f"{i}/{len(sample)} {part}: {mark} "
                  f"{row.get('before','-')}->{row.get('after','-')} segs "
                  f"[{row.get('secs','-')}s]", flush=True)
    print(f"\nsample {len(sample)}: changed {changed}, unchanged {same}, "
          f"errors {failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
