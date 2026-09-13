#!/usr/bin/env python3
"""The redraw queue, from a shell.

    .venv/bin/python scripts/render-requests.py pending --slot occt
    .venv/bin/python scripts/render-requests.py pending --slot occt \
        --into out/slot-occt-r9/batches.txt

`pending` prints, as its last line, how many parts are waiting on a redraw in
the slot. With `--into` it also puts them at the front of that batch list --
creating it when the gap selection wrote none -- and prints ENGINE, SOURCE and
EXTRA the way slot-coverage does, so a round made only of requests launches
with the slot's own flags.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db, requests  # noqa: E402


def _slot_flags(slot: str) -> dict:
    spec = importlib.util.spec_from_file_location(
        "slot_coverage", ROOT / "scripts" / "slot-coverage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.flags_for(slot)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pending", help="parts waiting on a redraw in a slot")
    p.add_argument("--slot", required=True)
    p.add_argument("--into", type=Path,
                   help="batch list to put the requested parts at the front of")
    p.add_argument("--per-batch", type=int, default=12)
    p.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    p.add_argument("--requests", default=str(ROOT / requests.DEFAULT_PATH))
    a = ap.parse_args(argv)

    if a.slot not in db.SOURCES:
        ap.error(f"unknown slot {a.slot!r}; one of {', '.join(db.SOURCES)}")
    conn = db.connect(a.db)
    try:
        parts = requests.pending(conn, a.slot, a.requests)
    finally:
        conn.close()

    if a.into and parts:
        lines = a.into.read_text().splitlines() if a.into.is_file() else []
        a.into.parent.mkdir(parents=True, exist_ok=True)
        a.into.write_text(
            "\n".join(requests.front_load(lines, parts, a.per_batch)) + "\n")
        flags = _slot_flags(a.slot)
        print(f"  ENGINE={flags['engine']}", flush=True)
        print(f"  SOURCE={a.slot}", flush=True)
        print(f"  EXTRA='{flags['extra']}'", flush=True)
    print(len(parts), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
