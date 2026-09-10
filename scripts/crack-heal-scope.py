#!/usr/bin/env python3
"""Which parts the crack repair can move, without drawing any of them.

    .venv/bin/python scripts/crack-heal-scope.py --parts out/scope.txt \
        --out out/crack-heal-scope.jsonl

`heal_face_cracks` returns the shape it was handed when it heals nothing, so a
part whose faces keep every inner wire goes down an identical pipeline and
draws an identical picture. That makes `faces_healed` a sound over-estimate of
the parts a re-render would change -- sound by construction rather than by
sample -- and it costs a shape build rather than a render: no HLR, no
decoration, no fill, no raster.

Reports one line per part as it goes. `--skip-done` resumes from the JSONL,
because OCCT segfaults on some parts and takes the process down with it -- the
same reason census-shard.sh runs its worker in a restart loop.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import config, db, occt, timing  # noqa: E402


def sample_from_corpus(n: int, seed: int) -> list[str]:
    conn = sqlite3.connect(ROOT / db.DEFAULT_PATH)
    marks = ",".join("?" * len(db.OUT_OF_SCOPE_CATEGORIES))
    ids = [r[0] for r in conn.execute(
        f"SELECT id FROM parts WHERE obsolete=0 AND (category IS NULL OR "
        f"category NOT IN ({marks}))", db.OUT_OF_SCOPE_CATEGORIES)]
    random.seed(seed)
    return random.sample(ids, min(n, len(ids)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", help="ids to probe, one per line")
    ap.add_argument("--batch", help="comma-separated ids, for onto's item "
                                    "dispatch; names its own JSONL under --dir")
    ap.add_argument("--dir", help="write <first part>.jsonl here, for --batch")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="out/crack-heal-scope.jsonl")
    ap.add_argument("--skip-done", action="store_true",
                    help="append, skipping parts the JSONL already has")
    args = ap.parse_args()

    if args.batch:
        parts = [x for x in args.batch.split(",") if x]
    elif args.parts:
        parts = [l.strip() for l in Path(args.parts).read_text().splitlines()
                 if l.strip()]
    else:
        parts = sample_from_corpus(args.n, args.seed)

    # One JSONL per batch, named for its first part. Batches sharing a file
    # would also share the .inflight marker below, so a crash in one would
    # name a part from another.
    if args.dir:
        d = Path(args.dir)
        d.mkdir(parents=True, exist_ok=True)
        args.out = str(d / f"{parts[0]}.jsonl")

    ldraw = config.load_config().ldraw_dir
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    done: set[str] = set()
    if args.skip_done and outp.exists():
        for line in outp.read_text().splitlines():
            try:
                done.add(json.loads(line)["part"])
            except (ValueError, KeyError):
                continue
        parts = [p for p in parts if p not in done]
        print(f"resuming: {len(done)} done, {len(parts)} left", flush=True)

    # The watchdog outside this process reads this file's mtime to learn when
    # the current part started; a part inside one long OCCT call runs past any
    # in-process alarm, so killing from outside is the only cap that holds.
    inflight = outp.with_suffix(outp.suffix + ".inflight")
    healed = clean = failed = 0
    with outp.open("a" if args.skip_done else "w") as fh:
        for i, part in enumerate(parts, 1):
            t0 = time.time()
            row = {"part": part}
            inflight.write_text(part)
            try:
                timing.reset()
                out = occt.flatten_part(part, ldraw)
                occt.build_shape(out)
                c = timing.counts()
                n = c.get("faces_healed", 0)
                row.update(faces_healed=n, unify_crash=c.get("unify_crash", 0),
                           secs=round(time.time() - t0, 2))
                healed += bool(n)
                clean += not n
            except Exception as e:
                row.update(error=type(e).__name__, detail=str(e)[:200])
                failed += 1
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            mark = ("HEALED" if row.get("faces_healed") else
                    "error" if "error" in row else "clean")
            print(f"{i}/{len(parts)} {part}: {mark} "
                  f"[{row.get('secs','-')}s]", flush=True)
    print(f"\nprobed {len(parts)}: healed {healed}, clean {clean}, "
          f"errors {failed}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
