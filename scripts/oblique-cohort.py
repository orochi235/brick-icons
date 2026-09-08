#!/usr/bin/env python3
"""Parts holding a cyli or con whose axis leaves the cross-section plane.

    .venv/bin/python scripts/oblique-cohort.py --limit 400 --out out/oblique-cohort.txt

`skew-deg` in `part_features` is the max over every primitive INCLUDING the
planar ones, whose axis column is not read at all -- so it names a far wider
cohort than the walls this touches. This resolves each candidate and asks
`occt.frame` the same question `occt_faces` does.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import config, db, occt  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--min-skew", type=float, default=1.0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    conn = db.connect(args.db)
    rows = conn.execute(
        "SELECT part_id FROM part_features WHERE feature='skew-deg' "
        "AND CAST(value AS REAL) >= ? ORDER BY CAST(value AS REAL) DESC",
        (args.min_skew,)).fetchall()
    ids = [r[0] for r in rows][: args.limit or None]
    ldraw = config.load_config().ldraw_dir
    hits, kinds = [], {}
    t0 = time.perf_counter()
    for i, pid in enumerate(ids, 1):
        try:
            out = occt.flatten_part(pid, ldraw)
        except Exception:
            continue
        n = 0
        for p in out["analytic"]:
            if p.kind in ("cyli", "con") and occt.frame(p) is None:
                n += 1
                kinds[p.kind] = kinds.get(p.kind, 0) + 1
        if n:
            hits.append((pid, n))
        if i % 25 == 0:
            print(f"{i}/{len(ids)}  {len(hits)} parts with an oblique wall  "
                  f"{time.perf_counter() - t0:5.1f}s", flush=True)
    print(f"{len(hits)} of {len(ids)} candidates hold an oblique cyli/con; "
          f"by kind {kinds}")
    for pid, n in sorted(hits, key=lambda r: -r[1])[:20]:
        print(f"  {pid:<16} {n}")
    if args.out:
        args.out.write_text("\n".join(p for p, _ in hits) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
