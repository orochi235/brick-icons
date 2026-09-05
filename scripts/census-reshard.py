#!/usr/bin/env python3
"""Re-split one engine's unfinished census work into N fresh shards.

    scripts/census-reshard.py <engine> <n>

The corpus is split per engine rather than shared, because the two engines run
at different rates and are rarely the same distance through. A part already
recorded in any of that engine's JSONL files is left out, so the new shards
carry only work nobody has done and each starts with an empty --skip-done set.
Old JSONL files stay as the record; census-report.py globs *.jsonl.
"""
import json
import sys
from pathlib import Path

DIR = Path("out/census")


def main() -> int:
    engine, n = sys.argv[1], int(sys.argv[2])
    corpus = DIR.joinpath("order.txt").read_text().split()

    done = set()
    for f in DIR.glob(f"{engine}-*.jsonl"):
        for line in f.open(errors="ignore"):
            try:
                done.add(json.loads(line)["part"])
            except (json.JSONDecodeError, KeyError):
                continue

    left = [p for p in corpus if p not in done]
    for i in range(n):
        shard = left[i::n]
        DIR.joinpath(f"{engine}-r{i}.txt").write_text("\n".join(shard) + "\n")
        print(f"{engine}-r{i}: {len(shard)} parts")
    print(f"{engine}: {len(done)} already done, {len(left)} split across {n} shards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
