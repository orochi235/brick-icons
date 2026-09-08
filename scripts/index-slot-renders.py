#!/usr/bin/env python3
"""Index a slot's renders where they already lie, without rebuilding the db.

    .venv/bin/python scripts/index-slot-renders.py --source reference

`db.rebuild` indexes `renders/**` too, but it drops the database first and
reseeds parts, features, defects and every census tree with it. A slot that was
baked outside the CLI -- `reference` comes out of a browser, 24,589 files in one
run -- needs its rows and nothing else disturbed.

Resumable: a part already indexed under the source is skipped, so a killed run
continues by being run again. `--force` reindexes anyway, which is what a
re-bake of the same slot needs.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402


def index(conn: sqlite3.Connection, source: str, root: Path | str = ".",
          force: bool = False, progress=print) -> dict[str, int]:
    root = Path(root)
    made = root / "renders" / source
    if not made.is_dir():
        raise FileNotFoundError(f"no renders at {made}")

    known = {r["id"] for r in conn.execute("SELECT id FROM parts")}
    have = set() if force else {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (source,))}

    files = sorted(p for p in made.iterdir() if p.suffix in db.RENDER_SUFFIXES)
    counts = {"indexed": 0, "skipped": 0, "unknown": 0, "failed": 0}
    progress(f"onto: plan 0/{len(files)}")
    for i, path in enumerate(files, 1):
        pid = path.stem
        if pid not in known:
            counts["unknown"] += 1
            continue
        if pid in have:
            counts["skipped"] += 1
            continue
        try:
            db.record_render(conn, pid, source, path, root=root)
        except Exception as e:  # noqa: BLE001
            counts["failed"] += 1
            progress(f"  {i}/{len(files)} {pid}: {type(e).__name__} {e}")
            continue
        counts["indexed"] += 1
        progress(f"  {i}/{len(files)} {pid}")
    progress(f"onto: progress {counts['indexed']}/{len(files)}")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                    help=f"slot to index; one of {', '.join(db.SOURCES)}")
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--force", action="store_true",
                    help="reindex parts already recorded under the source")
    args = ap.parse_args()
    if args.source not in db.SOURCES:
        ap.error(f"unknown source {args.source!r}; one of {', '.join(db.SOURCES)}")

    conn = db.connect(args.db)
    try:
        counts = index(conn, args.source, root=args.root, force=args.force)
    finally:
        conn.close()
    print(f"{args.source}: indexed {counts['indexed']}, "
          f"already had {counts['skipped']}, "
          f"not a known part {counts['unknown']}, failed {counts['failed']}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
