#!/usr/bin/env python
"""Stamp every open defect with the renders it was last judged against.

A defect asks for review once a slot draws something other than what its
`checked` says. Records filed before that field have no baseline and so never
ask -- this sets one, at today's renders, which reads as "looked at just now"
and leaves the wall quiet until something actually changes.

Run once after the field lands. Running it again re-baselines, which throws
away every outstanding review request, so it asks first.
"""
from __future__ import annotations

import argparse
import sys

from brick_icons import db as corpus_db
from brick_icons.lab import cells, defects


def slots_for(conn, engines: list[str]) -> list[str]:
    """Every slot drawn by one of these engines. A defect names an engine, and
    both `silhouette-naive` and `white-naive` are the naive engine drawing."""
    return sorted(r["source"] for r in conn.execute(
        "SELECT DISTINCT source FROM renders")
        if cells.engine_for(r["source"]) in engines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=corpus_db.DEFAULT_PATH)
    ap.add_argument("--defects", default=defects.DEFAULT_PATH)
    ap.add_argument("--all", action="store_true",
                    help="re-stamp records that already carry `checked`, "
                         "discarding any review they are currently asking for")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    conn = corpus_db.connect(args.db)
    records = defects.load(args.defects)
    open_records = [r for r in records
                    if r.get("status", "open") not in ("fixed", "notabug")]
    print(f"{len(open_records)} live of {len(records)} defects")

    changed = 0
    for i, record in enumerate(open_records, 1):
        if record.get("checked") and not args.all:
            print(f"{i}/{len(open_records)} {record['id']} — already stamped")
            continue
        stamp = {}
        for source in slots_for(conn, record.get("engines", [])):
            row = conn.execute(
                "SELECT sha256 FROM renders WHERE source = ? AND part_id = ?",
                (source, record["part"])).fetchone()
            if row:
                stamp[source] = row["sha256"]
        print(f"{i}/{len(open_records)} {record['id']} — {len(stamp)} slot(s)")
        if stamp:
            record["checked"] = stamp
            changed += 1

    if args.dry_run:
        print(f"would stamp {changed}; nothing written")
        return 0
    defects.save(args.defects, records)
    for record in records:
        corpus_db.upsert_defect(conn, record)
    print(f"stamped {changed}; wrote {args.defects} and {args.db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
