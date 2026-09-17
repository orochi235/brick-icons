#!/usr/bin/env python3
"""Enter displacements that happened before the review log existed.

    .venv/bin/python scripts/review-backfill.py --slot occt --previous renders/occt
    .venv/bin/python scripts/review-backfill.py --slot occt --previous renders/occt --dry-run

`record_render` logs a displacement as it happens, so a round ingested since
the log existed needs nothing from this. A round ingested before it left the
displaced drawings behind in the tree the slot used to point at -- each fleet
round writes its own `out/<task>/` tree and the store lives in `renders/` --
and this walks that tree: every part whose current row is drawn elsewhere
with a different sha gets a `replaced` line, before being the file here.

The before's made-at is the file's mtime and its run is unknown; both are
honest about what a backfill can know.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, goldens, review  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("--previous", required=True, type=Path,
                    help="the tree the slot pointed at before the round, "
                         "relative to the repository root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT,
                    help="the checkout whose renders, log and corpus.db this "
                         "reads and writes (default: this one)")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    root = a.root.resolve()
    previous = (root / a.previous).resolve()
    conn = db.connect(a.db or root / db.DEFAULT_PATH)
    log = root / review.DEFAULT_PATH
    rows = conn.execute(
        "SELECT part_id, path, sha256, run_id FROM renders WHERE source = ? "
        "ORDER BY part_id", (a.slot,)).fetchall()
    seen = moved = 0
    try:
        for row in rows:
            now = root / row["path"]
            if now.resolve().parent == previous:
                continue
            candidates = list(previous.glob(f"{row['part_id']}.*"))
            if not candidates:
                continue
            old = candidates[0]
            seen += 1
            sha = goldens.sha256(old.read_bytes())
            if sha == row["sha256"]:
                continue
            moved += 1
            made = datetime.fromtimestamp(old.stat().st_mtime, timezone.utc)
            print(f"{moved} {row['part_id']}: {old.relative_to(root)} -> "
                  f"{row['path']}", flush=True)
            if a.dry_run:
                continue
            review.record_replaced(
                conn, root, log, part=row["part_id"], source=a.slot,
                before={"path": str(old.relative_to(root)), "sha256": sha,
                        "made_at": made.isoformat(timespec="seconds"),
                        "run_id": None},
                after={"path": row["path"], "sha256": row["sha256"]},
                run_id=row["run_id"], by=review.by_from_path(row["path"]))
    finally:
        conn.close()
    print(f"{len(rows)} in the slot, {seen} also in {a.previous}, {moved} "
          f"differ{' (dry run, nothing written)' if a.dry_run else ''}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
