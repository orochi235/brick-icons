#!/usr/bin/env python3
"""Render one batch of parts through LDView into a reference slot's tree.

    .venv/bin/python scripts/ldview-batch.py --look gray \\
        --source reference-gray --dir out/slot-reference-gray 3001,3002

    scripts/refill-slot.sh reference-gray keiei slot-reference-gray

The tree is laid out the way a census tree is, so `ingest-watch.py` and
`db.rebuild` take it up unchanged: `SOURCE` names the slot, drawings land at
`renders/ldview/<part>.webp`, and one JSONL per batch (named for its first
part) holds a row per part in the census's measurement shape -- `secs`, the
`render` phase, `build`, and `error`/`detail` on a part LDView could not
draw. A row for every part, drawn or not, is what lets `slot-coverage.py`
tell "never tried" from "tried and failed" for the next round.

A batch rather than a part because LDView draws one in about half a second
and a fresh interpreter costs most of that again. Resumable: a part already
in the tree is skipped, and one that fails or hangs is a row rather than the
end of its batch.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import brick_icons  # noqa: E402
from brick_icons import cli  # noqa: E402
from brick_icons.config import load_config  # noqa: E402

ENGINE = "ldview"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="comma-separated part ids")
    ap.add_argument("--look", default="color", choices=("color", "gray", "lines"))
    ap.add_argument("--source", required=True, help="the slot, for the tree's SOURCE marker")
    ap.add_argument("--dir", required=True, help="the tree to write into")
    ap.add_argument("--timeout", type=float, default=120)
    args = ap.parse_args()

    tree = Path(args.dir)
    out = tree / "renders" / ENGINE
    out.mkdir(parents=True, exist_ok=True)
    marker = tree / "SOURCE"
    if not marker.exists():
        tmp = tree / f".SOURCE.{time.time_ns()}"
        tmp.write_text(args.source + "\n")
        tmp.replace(marker)

    ids = [s for s in (t.strip() for t in args.batch.split(",")) if s]
    jsonl = tree / f"{ENGINE}-{ids[0]}.jsonl"
    logged = set()
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            if line.strip():
                logged.add(json.loads(line)["part"])
    todo = [p for p in ids if p not in logged and not (out / f"{p}.webp").exists()]
    done, total = len(ids) - len(todo), len(ids)
    # onto reads these off this item's own pipe: without them a 25-part batch
    # is a bar that moves once, when the batch ends.
    print(f"onto: plan {done}/{total}", flush=True)

    # Through the CLI's own config path, labels.toml included: a slot drawn
    # under different defaults from the parts already in it is not one slot.
    cfg = load_config(toml_path=ROOT / "labels.toml", root=ROOT,
                      overrides={"use_ldview": True, "ldview_look": args.look,
                                 "angle": "iso"})
    build = brick_icons.build()
    bad = 0
    with jsonl.open("a") as log:
        for pid in todo:
            print(f"onto: item {pid}", flush=True)
            t0 = time.monotonic()
            row = {"part": pid, "engine": ENGINE, "angle": "iso",
                   "look": args.look, "build": build}
            try:
                cli.process_one(cfg, pid, out, timeout=args.timeout)
                state = "ok"
            except subprocess.TimeoutExpired as e:
                bad += 1
                row["error"], row["detail"] = "TimeoutError", str(e)[:300]
                state = "FAILED TimeoutError"
            except Exception as e:  # noqa: BLE001
                bad += 1
                row["error"] = type(e).__name__
                row["detail"] = str(e).splitlines()[0][:300] if str(e) else ""
                state = f"FAILED {row['error']}: {row['detail'][:120]}"
            secs = time.monotonic() - t0
            row["secs"] = round(secs, 1)
            row["phase"] = {"render": round(secs, 2)}
            log.write(json.dumps(row) + "\n")
            log.flush()
            done += 1
            print(f"{done}/{total} {pid}: {state} [{secs:.1f}s]", flush=True)
            print(f"onto: progress {done}/{total}", flush=True)
            if bad:
                print(f"onto: failed {bad}/{total}", flush=True)
    return 1 if bad == len(todo) and todo else 0


if __name__ == "__main__":
    raise SystemExit(main())
