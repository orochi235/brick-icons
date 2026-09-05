#!/usr/bin/env python3
"""Rebuild corpus.db from the files that are the actual artifacts.

    .venv/bin/python scripts/build-corpus-db.py

The database is derived: this deletes and rewrites it from `renders/`, the
census JSONL and the git-tracked TOML. Nothing here renders anything.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--census-dir", default=str(ROOT / "out" / "census"))
    args = ap.parse_args()

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    counts = db.rebuild(args.out, ldraw_dir=load_config().ldraw_dir, root=ROOT,
                        census_dir=args.census_dir, commit_sha=sha or "unknown",
                        progress=lambda m: print(m, flush=True))
    print(", ".join(f"{v} {k}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
