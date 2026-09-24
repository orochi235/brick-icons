#!/usr/bin/env python3
"""Retire review entries nobody is going to judge, and reap what they kept.

    .venv/bin/python scripts/flush-review.py --older-than 3 --dry-run
    .venv/bin/python scripts/flush-review.py --older-than 3

Only UNJUDGED entries are dropped: a verdict is the record of someone having
looked, and nothing here throws that away.

Every displacement copies the drawing it wrote over into `store-queue/before/`
so the Review page has a left-hand panel. Nothing ever removed those, and they
reached 1.5 GB against a 16 MB log. A kept copy is reaped only once no
surviving entry names it -- several entries can name one file, and a judged
entry still needs its panel -- so the sweep is over the whole table, not over
the rows being dropped.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, review  # noqa: E402


def stale(conn, days: float) -> list[str]:
    """Unjudged entries older than `days`, oldest first."""
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return [r["id"] for r in conn.execute(
        "SELECT id FROM review WHERE verdict IS NULL AND at < ? "
        "ORDER BY at", (cut,))]


def unreferenced(conn, root: Path, excluding: set[str] = frozenset()) -> list[Path]:
    """Kept before-copies no surviving entry names.

    `excluding` is the ids a dry run is about to drop but has not: without it
    the one mode whose job is to report the cost reports none of it.
    """
    named = {r["before_kept"] for r in conn.execute(
        "SELECT id, before_kept FROM review WHERE before_kept IS NOT NULL")
        if r["id"] not in excluding}
    live = {(root / rel).resolve() for rel in named}
    out = []
    for slot in sorted((root / review.BEFORE_DIR).glob("*")):
        if not slot.is_dir():
            continue
        out += [p for p in sorted(slot.iterdir())
                if p.is_file() and p.resolve() not in live]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--older-than", type=float, default=3,
                    help="drop unjudged entries older than this many days")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    conn = db.connect()
    log = args.root / review.DEFAULT_PATH
    doomed = stale(conn, args.older_than)
    kept_total = sum(1 for _ in (args.root / review.BEFORE_DIR).glob("*/*"))
    print(f"{len(doomed)} unjudged entries older than {args.older_than}d "
          f"(of {conn.execute('SELECT COUNT(*) n FROM review').fetchone()['n']} "
          f"entries, {kept_total} kept befores)")

    if args.dry_run:
        for eid in doomed[:5]:
            print(f"  would drop {eid}")
        if len(doomed) > 5:
            print(f"  ... and {len(doomed) - 5} more")
    else:
        for i, eid in enumerate(doomed, 1):
            review.record_dropped(conn, log, eid, by="flush")
            if i % 500 == 0 or i == len(doomed):
                print(f"  dropped {i}/{len(doomed)}", flush=True)

    orphans = unreferenced(conn, args.root,
                           set(doomed) if args.dry_run else set())
    freed = sum(p.stat().st_size for p in orphans)
    print(f"{len(orphans)} kept befores now unreferenced, {freed / 2**20:.0f} MiB")
    if not args.dry_run:
        for i, p in enumerate(orphans, 1):
            p.unlink()
            if i % 1000 == 0 or i == len(orphans):
                print(f"  reaped {i}/{len(orphans)}", flush=True)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
