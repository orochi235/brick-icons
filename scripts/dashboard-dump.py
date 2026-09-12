#!/usr/bin/env python
"""Write every number the stats dashboard draws, straight from corpus.db.

One JSON file per working set, the same `stats.stats()` the lab's
`/api/corpus/stats` serves -- so a dumped panel and a drawn one cannot
disagree. Nothing here recomputes a tally: `tallies` is a series of snapshots
taken at ingest and a past count cannot be derived from the database as it
stands now.

    scripts/dashboard-dump.py --out out/dashboard
    scripts/dashboard-dump.py --kind all --db corpus.db
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import db  # noqa: E402
from brick_icons.lab import stats  # noqa: E402


def digest(answer: dict) -> str:
    """The line a reader scans: how big the set is and what the panels hold."""
    cost = answer.get("cost")
    slots = f"{len(cost['slots'])} slots vs {cost['base']}" if cost else "no cost"
    return (f"{answer['set']['size']:,} parts, "
            f"{len(answer['coverage'])} coverage rows, {slots}, "
            f"{len(answer['speed'])} timed engines")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="dashboard-dump")
    p.add_argument("--db", default=str(db.DEFAULT_PATH))
    p.add_argument("--out", type=Path, default=Path("out/dashboard"),
                   help="directory to write <kind>.json into")
    p.add_argument("--kind", action="append", choices=stats.KINDS,
                   help="one working set (repeatable); default is every kind")
    args = p.parse_args(argv)

    kinds = args.kind or list(stats.KINDS)
    args.out.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)
    try:
        for i, kind in enumerate(kinds, 1):
            started = time.monotonic()
            answer = stats.stats(conn, kind=kind)
            path = args.out / f"{kind}.json"
            path.write_text(json.dumps(answer, indent=1, sort_keys=True))
            print(f"{i}/{len(kinds)} {kind}: {digest(answer)} "
                  f"-- {time.monotonic() - started:.1f}s -> {path}", flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
