#!/usr/bin/env python3
"""Render one batch of parts through LDView, into the reference slot.

    onto run --detach --in brick-icons --each out/ldview/batches.txt \
      --out renders/ldview --to renders/ldview studio \
      -- .venv/bin/python scripts/ldview-batch.py {}

A batch rather than a part because LDView draws one in about half a second
and a fresh interpreter costs most of that again. Resumable: a part whose
.webp is already in the slot is skipped, and one that fails or hangs is left
behind rather than taking the rest of its batch with it.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli  # noqa: E402
from brick_icons.config import load_config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", help="comma-separated part ids")
    ap.add_argument("--out", default="renders/ldview")
    ap.add_argument("--timeout", type=float, default=120)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ids = [s for s in (t.strip() for t in args.batch.split(",")) if s]
    todo = [p for p in ids if not (out / f"{p}.webp").exists()]
    done, total = len(ids) - len(todo), len(ids)
    # onto reads these off this item's own pipe: without them a 25-part batch
    # is a bar that moves once, when the batch ends.
    print(f"onto: plan {done}/{total}", flush=True)

    # Through the CLI's own config path, labels.toml included: a slot drawn
    # under different defaults from the 3,896 already in it is not one slot.
    cfg = load_config(toml_path=ROOT / "labels.toml", root=ROOT,
                      overrides={"use_ldview": True, "angle": "iso"})
    bad = 0
    for pid in todo:
        print(f"onto: item {pid}", flush=True)
        t0 = time.monotonic()
        try:
            cli.process_one(cfg, pid, out, timeout=args.timeout)
            state = "ok"
        except Exception as e:  # noqa: BLE001
            bad += 1
            state = f"FAILED {type(e).__name__}: {str(e).splitlines()[0][:120]}"
        done += 1
        print(f"{done}/{total} {pid}: {state} [{time.monotonic() - t0:.1f}s]",
              flush=True)
        print(f"onto: progress {done}/{total}", flush=True)
        if bad:
            print(f"onto: failed {bad}/{total}", flush=True)
    return 1 if bad == len(todo) and todo else 0


if __name__ == "__main__":
    raise SystemExit(main())
