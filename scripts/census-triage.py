#!/usr/bin/env python3
"""Split a finished census run's corpus into work worth redoing and work that isn't.

    scripts/census-triage.py <archive-dir> <engine> <n>
    scripts/census-triage.py <archive-dir> <engine> --corpus LIST --out LIST

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

The second form is one pass of the watchdog ratchet. `census-shard.sh` kills a
part that outlives HARD and the restart loop buries it as ProcessDied, so a pass
leaves some of its input undone; this reads that pass's own list as the corpus
and writes what is still undone as the next pass's list, to be run at a higher
HARD. The set shrinks each pass and nothing is discarded — a part the ceiling
killed comes back rather than being ruled out:

    HARD=240 scripts/census-shard.sh occt h240 120
    scripts/census-triage.py out/census occt \\
        --corpus out/census/occt-h240.txt --out out/census/occt-h480.txt
    HARD=480 scripts/census-shard.sh occt h480 120

Stop when the count stops falling: what is left then is parts the engine cannot
draw, not parts it was not given long enough to draw.
"""
import argparse
import json
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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    ap.add_argument("engine")
    ap.add_argument("n", nargs="?", type=int, help="number of shards to split into")
    ap.add_argument("--corpus", type=Path, default=DIR / "order.txt",
                    help="list file to triage against (default out/census/order.txt)")
    ap.add_argument("--out", type=Path,
                    help="write the still-undone parts here as one ratchet pass")
    args = ap.parse_args()
    if args.out is None and args.n is None:
        ap.error("give <n> to split into shards, or --out for one ratchet pass")

    archive, engine = args.archive, args.engine
    corpus = args.corpus.read_text().split()

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

    if args.out:
        return ratchet(engine, corpus, good, bad, args.corpus, args.out)

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
    for i in range(args.n):
        shard = keep[i::args.n]
        DIR.joinpath(f"{engine}-r{i}.txt").write_text("\n".join(shard) + "\n")
        print(f"{engine}-r{i}: {len(shard)} parts")

    why = Counter(bad[p] for p in degenerate)
    print(f"{engine}: {len(corpus)} in corpus, {len(degenerate)} degenerate, {len(keep)} to run")
    print(f"{engine}: never attempted = {len(keep) - len(good)}")
    print(f"{engine}: {len(backfill)} measured but never drawn -> {engine}-backfill.txt")
    for err, count in why.most_common():
        print(f"  {err}: {count}")
    return 0


def ratchet(engine, corpus, good, bad, src: Path, out: Path) -> int:
    # Absence of a row is not success: a pass killed at its deadline leaves
    # parts it never reached, and testing `p in bad` instead would drop them
    # from every later pass without saying so.
    again = [p for p in corpus if p not in good]
    out.write_text("\n".join(again) + "\n" if again else "")

    why = Counter(bad.get(p, "(never attempted)") for p in again)
    done = len(corpus) - len(again)
    print(f"{engine}: {len(corpus)} in {src}, {done} done, {len(again)} to re-run -> {out}")
    for err, count in why.most_common():
        print(f"  {err}: {count}")
    if not again:
        print(f"{engine}: nothing left, the ratchet is done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
