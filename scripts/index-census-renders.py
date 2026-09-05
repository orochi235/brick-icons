#!/usr/bin/env python3
"""Index the renders the census kept, where they lie.

    .venv/bin/python scripts/index-census-renders.py --limit 100

The census's drawing is strokeless -- its fills carry the silhouette -- so it is
not the store's `naive` render and is never recorded as one. It is indexed under
`census-naive` and left in `out/`, which is what `db.rebuild` does with it too.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

ENGINE = "naive"
SOURCE = f"census-{ENGINE}"
KEPT = Path("out") / SOURCE / "renders" / ENGINE


def index(conn: sqlite3.Connection, root: Path | str = ".",
          limit: int = 100) -> int:
    """Record up to `limit` kept census renders. Returns how many it recorded."""
    root = Path(root)
    kept = root / KEPT
    if not kept.is_dir():
        raise FileNotFoundError(f"no census renders at {kept}")

    known = {r["id"] for r in conn.execute("SELECT id FROM parts")}
    have = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (SOURCE,))}
    recorded = 0
    for svg in sorted(kept.glob("*.svg")):
        if recorded >= limit:
            break
        pid = svg.stem
        if pid not in known or pid in have:
            continue
        try:
            db.record_render(conn, pid, SOURCE, svg, root=root)
        except Exception as e:  # noqa: BLE001
            # The census is still running and kills shards mid-write, so a
            # truncated SVG is expected traffic, not a reason to stop.
            print(f"skipped {pid}: {type(e).__name__} {e}", flush=True)
            continue
        recorded += 1
        print(f"{recorded}/{limit} {pid}", flush=True)
    return recorded


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    conn = db.connect(args.db)
    try:
        n = index(conn, root=args.root, limit=args.limit)
    finally:
        conn.close()
    print(f"recorded {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
