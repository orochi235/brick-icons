#!/usr/bin/env python3
"""Land a render-store tree that came home on its own into the slot.

    .venv/bin/python scripts/land-store-tree.py out/ckpt3/studio --source occt

A fleet run of `build-render-store.py` writes its drawings under
`<tree>/renders/<source>/` and its outcomes to `<tree>/store.jsonl.<source>`,
and nothing carries either into the slot: `ingest-watch.py` reads census
JSONL, and `index-store-attempts.py` only looks under `out/store`. This does
both for one tree -- every drawing goes through `db.store_render`, which keeps
the displaced file aside and logs the displacement for `/review`, and the
tree's logs become its `attempts` run.

Resumable: a drawing whose bytes already sit in the slot is skipped, so a
killed run continues by being run again, and running it over a tree a fetch
is still filling only lands what is whole. Copying the files in by hand and
indexing with `index-slot-renders.py` would overwrite the displaced drawing
before anything kept it.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, review  # noqa: E402


def land(conn, tree: Path, source: str, root: Path, commit_sha: str,
         limit: int | None = None, progress=print) -> dict[str, int]:
    made = tree / "renders" / source
    if not made.is_dir():
        raise FileNotFoundError(f"no renders at {made}")
    where = db._relative(tree, root)
    by = review.by_from_path(where)
    run_id = db.store_run(conn, tree, root, commit_sha)
    counts = {"attempts": 0, "landed": 0, "displaced": 0, "same": 0,
              "unknown": 0, "failed": 0}
    for log in db.store_logs(tree):
        counts["attempts"] += db.import_store_jsonl(conn, run_id, log)

    known = {r["id"] for r in conn.execute("SELECT id FROM parts")}
    held = {r["part_id"]: (r["path"], r["sha256"]) for r in conn.execute(
        "SELECT part_id, path, sha256 FROM renders WHERE source = ?",
        (source,))}
    files = sorted(p for p in made.iterdir() if p.suffix in db.RENDER_SUFFIXES)
    if limit:
        files = files[:limit]
    progress(f"onto: plan 0/{len(files)}")
    for i, path in enumerate(files, 1):
        pid = path.stem
        if pid not in known:
            counts["unknown"] += 1
            continue
        sha = db.goldens.sha256(path.read_bytes())
        was = held.get(pid)
        dest = Path("renders") / source / path.name
        if was and was[1] == sha and was[0] == str(dest):
            counts["same"] += 1
            continue
        try:
            db.store_render(conn, pid, source, path, root=root, run_id=run_id,
                            by=by)
        except Exception as e:  # noqa: BLE001
            counts["failed"] += 1
            progress(f"  {i}/{len(files)} {pid}: {type(e).__name__} {e}")
            continue
        counts["landed"] += 1
        if was and was[1] != sha:
            counts["displaced"] += 1
        progress(f"onto: progress {i}/{len(files)}")
    db.finish_run(conn, run_id, note=f"landed from {where}")
    return counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", help="store tree, e.g. out/ckpt3/studio")
    ap.add_argument("--source", required=True,
                    help=f"slot to land into; one of {', '.join(db.SOURCES)}")
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--limit", type=int, default=None,
                    help="land only the first N drawings (a dry run)")
    args = ap.parse_args()
    if args.source not in db.SOURCES:
        ap.error(f"unknown source {args.source!r}; one of {', '.join(db.SOURCES)}")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    conn = db.connect(args.db)
    try:
        counts = land(conn, Path(args.tree).resolve(), args.source,
                      Path(args.root).resolve(), sha or "unknown",
                      limit=args.limit)
    finally:
        conn.close()
    print(f"{args.tree} -> {args.source}: landed {counts['landed']} "
          f"(displaced {counts['displaced']}), already in slot {counts['same']}, "
          f"not a known part {counts['unknown']}, failed {counts['failed']}, "
          f"attempts {counts['attempts']}")
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
