#!/usr/bin/env python3
"""Split a finished census run's corpus into work worth redoing and work that isn't.

    scripts/census-triage.py <archive-dir> <engine> <n>

A part is degenerate for an engine when every row that engine recorded for it
carries an error — a 120s timeout, an OCCT segfault, a geometry exception. Those
cost a full timeout each and produce nothing, so they go in their own list and
come out of the shards.

Writes out/census/<engine>-degenerate.txt, which is a list file like any other:
pointing --list at it re-runs exactly the parts that failed, which is what you
want after raising --timeout or fixing the engine.

The rest of the corpus is split into <engine>-r<i>.txt. Unlike census-reshard.py
this keeps parts that already succeeded — the point of a re-run is the renders
--keep saves, which the first run drew and deleted.
"""
import json
import sys
from collections import Counter
from pathlib import Path

DIR = Path("out/census")
PROBE = 100


def rows(archive: Path, engine: str):
    for f in sorted(archive.glob(f"{engine}-*.jsonl")):
        for line in f.open(errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main() -> int:
    archive, engine, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    corpus = DIR.joinpath("order.txt").read_text().split()

    good, bad = set(), {}
    for i, row in enumerate(rows(archive, engine), 1):
        part = row.get("part")
        if not part:
            continue
        if "error" in row:
            bad.setdefault(part, row["error"])
        else:
            good.add(part)
        if i % 2000 == 0:
            print(f"  read {i} rows")

    # A part that failed once and succeeded later is not degenerate: the shard
    # restarts, and ProcessDied means the run died on it, not that it cannot be
    # drawn.
    degenerate = [p for p in corpus if p in bad and p not in good]
    keep = [p for p in corpus if p not in bad or p in good]

    DIR.joinpath(f"{engine}-degenerate.txt").write_text("\n".join(degenerate) + "\n")

    # Measured but never drawn: run 1 recorded numbers for these and deleted
    # every render. Re-running them with --keep against a fresh JSONL is the
    # backfill, and it is a different list from the shards above because those
    # also carry parts nobody has reached yet.
    backfill = [p for p in corpus if p in good]
    DIR.joinpath(f"{engine}-backfill.txt").write_text("\n".join(backfill) + "\n")

    # An evenly spaced sample of the degenerate set, for learning what a higher
    # --timeout actually buys before committing to the whole list. Evenly
    # spaced rather than random so the file is reproducible.
    if degenerate:
        step = max(1, len(degenerate) // PROBE)
        probe = degenerate[::step][:PROBE]
        DIR.joinpath(f"{engine}-probe{PROBE}.txt").write_text("\n".join(probe) + "\n")
    for i in range(n):
        shard = keep[i::n]
        DIR.joinpath(f"{engine}-r{i}.txt").write_text("\n".join(shard) + "\n")
        print(f"{engine}-r{i}: {len(shard)} parts")

    why = Counter(bad[p] for p in degenerate)
    print(f"{engine}: {len(corpus)} in corpus, {len(degenerate)} degenerate, {len(keep)} to run")
    print(f"{engine}: never attempted = {len(keep) - len(good)}")
    print(f"{engine}: {len(backfill)} measured but never drawn -> {engine}-backfill.txt")
    for err, count in why.most_common():
        print(f"  {err}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
