#!/usr/bin/env python
"""Which parts the decal slot would draw now that it did not draw before.

The slot records `state='none'` for a part it ran on and produced nothing.
This re-runs the decal path over exactly those parts and lists the ones that
now come back with a panel, so a re-render asks the fleet only for the work
that changed.

    scripts/decal-redo-list.py --jobs 10 --out out/decal-redo.csv

Runs the whole path, carrier route included, rather than only the new mesh
fallback: the fallback fires only where the carrier route finds nothing, and
that route has moved too since the census recorded these.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LDRAW = "vendor/ldraw"


def _panels(pid: str):
    from brick_icons import unwrap
    from brick_icons.hlr import part_geometry
    t0 = time.time()
    try:
        tri, cols, analytic = part_geometry(pid, LDRAW)
        n = len(unwrap.decal_panels(tri, cols, analytic))
        return pid, n, "", time.time() - t0
    except Exception as exc:
        return pid, 0, f"{type(exc).__name__}: {exc}"[:120], time.time() - t0


def owed(db: str, source: str) -> list[str]:
    conn = sqlite3.connect(db)
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT a.part_id FROM attempts a JOIN parts p "
        "ON p.id = a.part_id WHERE a.source = ? AND a.state = 'none' "
        "AND p.obsolete = 0 "
        "AND NOT EXISTS (SELECT 1 FROM renders r WHERE r.part_id = a.part_id "
        "                AND r.source = ?) ORDER BY a.part_id", (source, source))]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--parts-file", help="part ids, one per line, instead of "
                    "reading them out of the database -- what a fleet node "
                    "gets, so the job does not need a 186 MB corpus.db "
                    "shipped with it")
    ap.add_argument("--source", default="decal")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="out/decal-redo.csv")
    ap.add_argument("--list", dest="listing", default="out/decal-redo.txt",
                    help="the part ids that now draw, one per line")
    args = ap.parse_args(argv)

    parts = ([p.strip() for p in open(args.parts_file) if p.strip()]
             if args.parts_file else owed(args.db, args.source))
    if args.limit:
        parts = parts[:args.limit]
    print(f"{len(parts)} parts recorded as drawing nothing", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    draws: list[str] = []
    done = 0
    with out.open("w", newline="") as fh, \
            ProcessPoolExecutor(max_workers=args.jobs) as pool:
        w = csv.writer(fh)
        w.writerow(["part_id", "panels", "error", "secs"])
        for pid, n, err, secs in pool.map(_panels, parts, chunksize=1):
            done += 1
            if n:
                draws.append(pid)
            w.writerow([pid, n, err, f"{secs:.2f}"])
            fh.flush()
            note = err or (f"{n} panels" if n else "nothing")
            print(f"{done}/{len(parts)}  {pid:16s} {note}  ({secs:.1f}s)",
                  flush=True)

    Path(args.listing).write_text("".join(f"{p}\n" for p in draws))
    print(f"\n{len(draws)} of {len(parts)} now draw -> {args.listing}")
    print(f"  per-part detail -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
