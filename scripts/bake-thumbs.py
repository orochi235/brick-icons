#!/usr/bin/env python3
"""Bake the corpus wall's thumbnails and sprite sheets, one slot at a time.

    .venv/bin/python scripts/bake-thumbs.py
    .venv/bin/python scripts/bake-thumbs.py --source naive

A slot is one `db.SOURCES` entry -- an engine crossed with a style. Each gets
its own thumbnails and its own sheets under `out/thumbs/<source>/`. Idempotent:
a part whose render sha has not changed is skipped, so running this after each
batch of renders costs only the new ones.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, thumbs  # noqa: E402

DEFAULT_OUT = Path("out") / "thumbs"


def bake_source(conn, source: str, root: Path, out: Path,
                order: list[str]) -> tuple[int, int]:
    """Bake one slot. Returns (baked, total)."""
    rows = conn.execute(
        "SELECT part_id, path, sha256 FROM renders WHERE source = ? "
        "ORDER BY part_id", (source,)).fetchall()
    slot = out / source
    total, baked = len(rows), 0
    for i, row in enumerate(rows, 1):
        svg = root / row["path"]
        if not svg.is_file():
            print(f"  {source} {i}/{total} {row['part_id']} MISSING {row['path']}",
                  flush=True)
            continue
        made = thumbs.bake_part(row["part_id"], svg, slot, sha=row["sha256"])
        baked += bool(made)
        print(f"  {source} {i}/{total} {row['part_id']} "
              f"{'baked' if made else 'fresh'}", flush=True)
    for path in thumbs.compose(slot, order):
        print(f"  wrote {path}", flush=True)
    return baked, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", default=str(ROOT / DEFAULT_OUT))
    ap.add_argument("--source", action="append",
                    help="slot to bake; repeatable. Default: every slot with renders.")
    args = ap.parse_args()

    root, out = Path(args.root), Path(args.out)
    conn = db.connect(args.db)
    try:
        order = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
        sources = args.source or [
            r["source"] for r in conn.execute(
                "SELECT DISTINCT source FROM renders ORDER BY source")]
        print(f"{len(sources)} slot(s) over {len(order)} cells: "
              f"{', '.join(sources)}", flush=True)
        for n, source in enumerate(sources, 1):
            print(f"[{n}/{len(sources)}] {source}", flush=True)
            baked, total = bake_source(conn, source, root, out, order)
            print(f"[{n}/{len(sources)}] {source}: baked {baked} of {total}",
                  flush=True)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
