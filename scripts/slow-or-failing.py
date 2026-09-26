#!/usr/bin/env python3
"""The parts a slot draws slowly or not at all, as a batch list to rerun.

    .venv/bin/python scripts/slow-or-failing.py --out out/slot-occt-retry
    .venv/bin/python scripts/slow-or-failing.py --slow 200 --since 48

A part qualifies on its NEWEST row in the slot, measured within `--since`
hours: an error, or a drawing that took at least `--slow` seconds. `secs` is
the whole oracle pass -- render, rasterize, compare -- not the render alone.
Build the list at launch time, not before: an engine change that lands
between the two moves which parts belong on it.

Writes `todo.txt` (one part a line) and `batches.txt` (a dozen a line, what
`onto run --each` takes), slowest drawing first and failures last, so a round
cut short has spent its time on the parts most likely to finish.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

BATCH = 12


def select(conn: sqlite3.Connection, source: str, since_h: float,
           slow_s: float) -> tuple[list[tuple], list[tuple]]:
    """(slow, failing): (part, secs) and (part, error) on each newest row."""
    rows = conn.execute("""
        WITH latest AS (
          SELECT m.part_id, m.error, m.secs, r.started,
                 ROW_NUMBER() OVER (PARTITION BY m.part_id
                                    ORDER BY m.run_id DESC) AS rn
          FROM measurements m JOIN runs r ON r.id = m.run_id
          WHERE m.source = ?)
        SELECT part_id, error, secs FROM latest
        WHERE rn = 1 AND started >= strftime('%Y-%m-%dT%H:%M:%S',
                                             'now', ?)""",
        (source, f"-{since_h} hours")).fetchall()
    slow = sorted(((p, s) for p, e, s in rows if not e and (s or 0) >= slow_s),
                  key=lambda r: (-r[1], r[0]))
    failing = sorted((p, e) for p, e, _s in rows if e)
    return slow, failing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="occt", help="render slot (default occt)")
    ap.add_argument("--since", type=float, default=24,
                    help="hours back a part's newest row may be (default 24)")
    ap.add_argument("--slow", type=float, default=120,
                    help="seconds a drawing must have taken to count (default 120)")
    ap.add_argument("--out", type=Path, help="directory for todo.txt and batches.txt")
    ap.add_argument("--db", type=Path, default=None)
    a = ap.parse_args()
    conn = db.connect(a.db) if a.db else db.connect()
    try:
        slow, failing = select(conn, a.source, a.since, a.slow)
    finally:
        conn.close()
    parts = [p for p, _ in slow] + [p for p, _ in failing]
    print(f"{a.source}, newest row within {a.since:g}h: "
          f"{len(slow):5d} drew in >= {a.slow:g}s, {len(failing):5d} failing, "
          f"{len(parts):5d} in all")
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "todo.txt").write_text("".join(p + "\n" for p in parts))
        (a.out / "batches.txt").write_text("".join(
            ",".join(parts[i:i + BATCH]) + "\n"
            for i in range(0, len(parts), BATCH)))
        print(f"wrote {a.out}/todo.txt and batches.txt "
              f"({-(-len(parts) // BATCH)} batches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
