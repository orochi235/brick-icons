#!/usr/bin/env python3
"""Delete a finished store tree's logs, once the database holds their rows.

    .venv/bin/python scripts/prune-store-logs.py out/store/occt-studio
    .venv/bin/python scripts/prune-store-logs.py out/store/occt-studio --delete

Dry run unless `--delete`. Three things have to hold first, because a log is
two things at once -- the record we ingest and the resume state a relaunch
reads:

- No `.inflight` marker and nothing written recently: a live task's log is
  what stops the next launch redrawing everything it finished.
- Every row already in `attempts`, checked part by part.
- A corpus snapshot that holds the rows itself, so they survive the next
  `db.rebuild` -- which drops the database and, with the logs gone, cannot
  re-derive them. Checked by counting them in the snapshot, not by its date:
  a snapshot taken after the logs can still predate the ingest.
  `scripts/snap-corpus.sh` writes one.

The node keeps its own copy of the tree, so pruning here does not stop a
relaunch there from resuming.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

SNAPSHOTS = Path("out") / "snapshots"


def rows_in(log: Path) -> set[tuple[str, str]]:
    out = set()
    for line in log.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out.add((r["part"], r["source"]))
    return out


def snapshot_holding(root: Path, tree: Path, want: int) -> Path | None:
    """The newest snapshot that already holds this tree's rows, if any."""
    snaps = sorted((root / SNAPSHOTS).glob("*.db"),
                   key=lambda p: p.stat().st_mtime, reverse=True) \
        if (root / SNAPSHOTS).is_dir() else []
    for snap in snaps:
        conn = db.connect(snap)
        try:
            run_id = db.store_run(conn, tree, root, create=False)
            if run_id is None:
                continue
            held = conn.execute(
                "SELECT count(*) FROM attempts WHERE run_id = ?",
                (run_id,)).fetchone()[0]
        finally:
            conn.close()
        if held >= want:
            return snap
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", help="a directory under out/store")
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--delete", action="store_true",
                    help="actually remove the logs; otherwise this is a dry run")
    ap.add_argument("--quiet-for", type=float, default=30,
                    help="minutes a log must have gone unwritten to count as "
                         "finished")
    ap.add_argument("--force", action="store_true",
                    help="prune without a snapshot newer than the logs")
    args = ap.parse_args()

    root = Path(args.root)
    tree = Path(args.tree)
    if not tree.is_absolute():
        tree = root / tree
    logs = db.store_logs(tree)
    if not logs:
        print(f"no logs in {tree}")
        return 1

    # A marker is rewritten per item, so a fresh one is a live run. A stale
    # one is what a killed run leaves; it belongs to these logs and goes with
    # them.
    inflight = sorted(tree.glob("*.inflight"))
    fresh = [m for m in inflight
             if (time.time() - m.stat().st_mtime) / 60 < args.quiet_for]
    if fresh:
        print(f"refusing: {len(fresh)} inflight marker(s) written in the last "
              f"{args.quiet_for:.0f} min, the run is live ({fresh[0].name})")
        return 1

    newest = max(log.stat().st_mtime for log in logs)
    quiet_min = (time.time() - newest) / 60
    if quiet_min < args.quiet_for:
        print(f"refusing: last written {quiet_min:.0f} min ago, under the "
              f"{args.quiet_for:.0f} min this calls finished")
        return 1

    conn = db.connect(args.db)
    run_id = db.store_run(conn, tree, root, create=False)
    if run_id is None:
        print(f"refusing: nothing ingested from {tree}; run "
              f"scripts/index-store-attempts.py first")
        conn.close()
        return 1
    have = {(r["part_id"], r["source"]) for r in conn.execute(
        "SELECT part_id, source FROM attempts WHERE run_id = ?", (run_id,))}
    conn.close()

    want: set[tuple[str, str]] = set()
    for log in logs:
        want |= rows_in(log)
    missing = want - have
    if missing:
        print(f"refusing: {len(missing)} of {len(want)} rows are not in the "
              f"database, e.g. {sorted(missing)[:3]}")
        return 1

    snap = snapshot_holding(root, tree, len(have))
    if snap is None and not args.force:
        print("refusing: no snapshot in out/snapshots holds these rows; run "
              "scripts/snap-corpus.sh after the ingest, or pass --force")
        return 1

    size = sum(log.stat().st_size for log in logs)
    print(f"{tree}: {len(logs)} logs and {len(inflight)} stale marker(s), "
          f"{len(want)} rows, {size / 1e6:.1f} MB, all in run {run_id}")
    print(f"held by {snap}" if snap else "no snapshot; --force given")
    if not args.delete:
        print("dry run; pass --delete to remove them")
        return 0
    for path in [*logs, *inflight]:
        path.unlink()
    print(f"deleted {len(logs)} logs and {len(inflight)} markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
