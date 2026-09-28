#!/usr/bin/env python3
"""Render seconds for a fresh census run against what corpus.db holds.

    scripts/census-timing-diff.py out/stud-timing-all/rows
    scripts/census-timing-diff.py out/<run>/rows --source occt --db ../brick-icons/corpus.db

BEFORE is the `render` phase of each part's newest row for --source, AFTER the
same phase in the run's JSONL, so the two columns are one quantity. A part
whose newest row is an error (a timeout, mostly) shows the seconds that row ran
as `>N` -- the cap it hit, for a timeout -- and its ratio as a floor. FILL is how much of AFTER the fill step took.

Read the ratios and not the digits: the two sides were drawn on different
nodes under different load, and at different builds.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROLES = ("clear", "cut", "hidden", "fallback")


def after_rows(rows: Path) -> dict[str, dict]:
    out = {}
    for f in sorted(rows.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["part"]] = row
    return out


def before_row(db: sqlite3.Connection, source: str, part: str):
    return db.execute(
        "select json_extract(phases, '$.render'), error, secs from measurements "
        "where source = ? and part_id = ? order by run_id desc limit 1",
        (source, part)).fetchone()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rows", type=Path, help="directory of the run's census JSONLs")
    ap.add_argument("--source", default="occt", help="render source to read BEFORE from")
    ap.add_argument("--db", default="corpus.db")
    args = ap.parse_args()

    db = sqlite3.connect(f"file:{Path(args.db).resolve()}?immutable=1", uri=True)
    table = []
    for part, row in after_rows(args.rows).items():
        b = before_row(db, args.source, part)
        capped = b is None or b[1] is not None or b[0] is None
        before = 0.0 if b is None else (b[2] or 0.0) if capped else b[0]
        after = (row.get("phase") or {}).get("render")
        table.append((part, b is not None, capped, before, after, row))
    table.sort(key=lambda t: -(t[3] / t[4]) if t[4] else 0)

    print(f"{'part':<10} {'before':>7} {'after':>7} {'ratio':>8} {'fill':>7} "
          f"{'studs':>5} {'fall':>4}  note")
    for part, known, capped, before, after, row in table:
        counts = row.get("counts") or {}
        roles = [counts.get(f"studs_{r}", 0) for r in ROLES]
        b = "-" if not known else f">{before:.0f}" if capped else f"{before:.1f}"
        if after is None:
            print(f"{part:<10} {b:>7} {'-':>7} {'-':>8} {'-':>7} "
                  f"{sum(roles):5d} {roles[3]:4d}  {row.get('error', 'no render phase')}")
            continue
        ratio = "-" if not known else f"{'>' if capped else ''}{before / after:.1f}x"
        fill = (row.get("phase") or {}).get("render/fill", 0.0)
        print(f"{part:<10} {b:>7} {after:7.1f} {ratio:>8} {fill:7.1f} "
              f"{sum(roles):5d} {roles[3]:4d}")


if __name__ == "__main__":
    main()
