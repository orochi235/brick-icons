#!/usr/bin/env python3
"""Component-count every replaced render the review queue has not measured.

    .venv/bin/python scripts/review-diff.py
    .venv/bin/python scripts/review-diff.py --limit 200

The queue's "all changes" view gates on this number, and an entry made before
`ingest-watch.py --diff` existed, or by a watcher run without it, has none.
The lab measures an entry when its diff panel is first asked for; this does
the whole backlog at once, newest first, one line per entry as it lands.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, review  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after this many (default: all of them)")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="the checkout whose log and corpus.db this reads "
                         "and writes (default: this one)")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    root = a.root.resolve()
    conn = db.connect(a.db or root / db.DEFAULT_PATH)
    try:
        done, failed = review.measure_unmeasured(
            conn, root, root / review.DEFAULT_PATH, root / ".cache" / "review",
            a.limit, progress=lambda m: print(m, flush=True))
    finally:
        conn.close()
    print(f"measured {done}, {len(failed)} unmeasurable", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
