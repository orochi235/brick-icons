#!/usr/bin/env python3
"""Take up the render store's logs into a database that already exists.

    .venv/bin/python scripts/index-store-attempts.py

`db.rebuild` reads the same logs, but it drops the database and reseeds parts,
features, defects and every census tree with it. A store run that has just come
home needs its rows and nothing else disturbed.

Idempotent: a tree keeps one run, so running this again replaces the rows it
wrote rather than stacking a second copy.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()

    trees = db.store_trees(args.root)
    if not trees:
        print(f"no store logs under {Path(args.root) / 'out' / 'store'}")
        return 1
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()

    conn = db.connect(args.db)
    try:
        n = db.ingest_store(conn, args.root, sha or "unknown",
                            progress=lambda m: print(f"  {m}", flush=True))
        for row in conn.execute(
                "SELECT source, COALESCE(error, state) AS outcome, count(*) AS n "
                "FROM attempts GROUP BY 1, 2 ORDER BY n DESC"):
            print(f"{row['source']:>18} {row['outcome']:<14} {row['n']:>6}")
    finally:
        conn.close()
    print(f"took up {n} attempts from {len(trees)} tree(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
