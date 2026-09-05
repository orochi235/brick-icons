#!/usr/bin/env python3
"""Render every part in a list into the tracked store, one canonical drawing
per source.

    .venv/bin/python scripts/build-render-store.py --list out/census/parts.txt \
        --sources naive,occt --timeout 180 --log out/store/run.jsonl

Detach it: a foreground call dies at its caller's timeout no matter what the
process is doing. Resumable -- a part already in the log is skipped, and one
that segfaults the interpreter is buried rather than retried forever, which
occt makes necessary (92738, u9236c03, 76110p01 and u9105p01c04 all crash it).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402
from brick_icons.batch import Runner  # noqa: E402
from brick_icons.lab import cache  # noqa: E402
from brick_icons.lab import runner as lab_runner  # noqa: E402


def render_one(part: str, source: str, run_id: int, conn, force: bool) -> dict:
    dest = ROOT / "renders" / source / f"{part}.svg"
    if dest.exists() and not force:
        return {"part": part, "source": source, "state": "present"}
    argv = db.canonical_argv(part, source)
    lab_root = ROOT / cache.DEFAULT_ROOT
    result = lab_runner.render(argv, root=lab_root, force=force)
    if not result["ok"]:
        raise RuntimeError(result["error"])
    svgs = [a["name"] for a in result["artifacts"] if a["name"].endswith(".svg")]
    if not svgs:
        raise RuntimeError(f"render produced no SVG: "
                           f"{[a['name'] for a in result['artifacts']]}")
    made = cache.dir_for(argv, root=lab_root) / svgs[0]
    db.store_render(conn, part, source, made, root=ROOT, run_id=run_id)
    return {"part": part, "source": source,
            "state": "cached" if result["cached"] else "stored"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--sources", default="naive,occt")
    ap.add_argument("--timeout", type=float, default=180)
    ap.add_argument("--log", default=str(ROOT / "out" / "store" / "store.jsonl"))
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--force", action="store_true",
                    help="re-render a part already in the store")
    args = ap.parse_args()

    ids = list(args.parts)
    if args.list:
        ids += [s for line in Path(args.list).read_text().splitlines()
                if (s := line.split("#")[0].strip())]
    if not ids:
        ap.error("name at least one part, or pass --list")

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    for source in sources:
        db.canonical_argv(ids[0], source)  # reject a bad source before rendering

    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(args.db)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    run_id = db.start_run(conn, "render", {"sources": sources}, sha or "unknown")

    for source in sources:
        batch = Runner(f"{args.log}.{source}", timeout=args.timeout, key="part",
                       extra={"source": source})
        todo = batch.remaining(ids)
        print(f"{source}: {len(todo)} of {len(ids)} to render", flush=True)
        for n, part in enumerate(todo, 1):
            row = batch.run(part, lambda p, s=source: render_one(
                p, s, run_id, conn, args.force))
            state = row.get("error") or row.get("state")
            print(f"{n}/{len(todo)} {source} {part}: {state} [{row['secs']}s]",
                  flush=True)

    db.finish_run(conn, run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
