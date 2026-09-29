#!/usr/bin/env python3
"""Fill `measurements.bytes`, `objects` and `drawn_at` for rows ingested before
those columns existed, from the drawings still in each census tree.

    .venv/bin/python scripts/backfill-render-stats.py [--workers 8] [--db corpus.db]

Each run's tree is re-read shard by shard and every row goes through
`db.drawing_stats`, the rule ingest applies, so a file redrawn by a later run
into the same tree is left unclaimed rather than credited to the wrong row.
Resumable: only rows whose `bytes` is still null are looked at, so a killed run
continues by being run again.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402


def _shard(args: tuple[str, str]) -> list[tuple]:
    """(part, engine, bytes, objects, drawn_at) for each row of one shard
    whose drawing is still the one it measured."""
    tree, shard = args
    logged_at = Path(shard).stat().st_mtime
    out = []
    for line in Path(shard).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("error"):
            continue
        got = db.drawing_stats(tree, row, logged_at)
        if got[0] is not None:
            out.append((row["part"], row["engine"], *got))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(db.DEFAULT_PATH))
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    conn = db.connect(args.db)
    runs = []
    for r in conn.execute("SELECT id, args FROM runs WHERE kind = 'census'"):
        tree = json.loads(r["args"]).get("dir")
        owed = conn.execute(
            "SELECT count(*) FROM measurements WHERE run_id = ? "
            "AND bytes IS NULL AND error IS NULL", (r["id"],)).fetchone()[0]
        if tree and owed and Path(tree).is_dir():
            runs.append((r["id"], tree, owed))

    filled = 0
    with ProcessPoolExecutor(args.workers) as pool:
        for i, (run_id, tree, owed) in enumerate(runs, 1):
            shards = [(tree, str(s)) for s in sorted(Path(tree).rglob("*.jsonl"))]
            got = [row for rows in pool.map(_shard, shards, chunksize=8)
                   for row in rows]
            cur = conn.executemany(
                "UPDATE measurements SET bytes = ?, objects = ?, drawn_at = ? "
                "WHERE run_id = ? AND part_id = ? AND engine = ? "
                "AND bytes IS NULL",
                [(b, o, at, run_id, part, engine)
                 for part, engine, b, o, at in got])
            conn.commit()
            filled += cur.rowcount
            print(f"{i}/{len(runs)} run {run_id} {tree}: "
                  f"{cur.rowcount} of {owed} filled", flush=True)
    print(f"filled {filled} rows")


if __name__ == "__main__":
    main()
