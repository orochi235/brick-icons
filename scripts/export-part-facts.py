#!/usr/bin/env python3
"""Write every part's connection counts and size, for collego's classifier.

    .venv/bin/python scripts/export-part-facts.py              # out/part-facts.json
    .venv/bin/python scripts/export-part-facts.py 87087 3001   # just these, to stdout

One JSON object keyed by LDraw part id, each value a `PartFacts` record
(`brick_icons/facts.py` says what is counted). The file is written to a temp
name and renamed over the last one, so a reader never sees half a file and
there is only ever one. A line per part goes to stdout and to the `.log`
beside it, also replaced each run: id, milliseconds, and the record in brief.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import facts  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*", help="part ids; omitted, the whole library")
    ap.add_argument("--out", default=str(ROOT / "out" / "part-facts.json"))
    args = ap.parse_args()

    ldraw = load_config(root=ROOT).ldraw_dir
    if args.ids:
        got = dict(facts.build(ldraw, args.ids, progress=print))
        json.dump(got, sys.stdout, indent=1, sort_keys=True)
        print()
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp, log_tmp = out.with_suffix(".json.tmp"), out.with_suffix(".log.tmp")
    t0 = time.perf_counter()
    with log_tmp.open("w") as log:
        def progress(msg: str) -> None:
            print(msg, flush=True)
            log.write(msg + "\n")
        got = dict(facts.build(ldraw, progress=progress))
        secs = time.perf_counter() - t0
        progress(f"done: {len(got)} parts in {secs:.1f}s "
                 f"({1000 * secs / max(len(got), 1):.2f} ms/part)")
    with tmp.open("w") as fh:
        json.dump(got, fh, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, out)
    os.replace(log_tmp, out.with_suffix(".log"))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
