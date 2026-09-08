#!/usr/bin/env python3
"""Count how many drawn elements `_snap_rim_crossings` costs each part.

    .venv/bin/python scripts/snap-element-delta.py

Reads the SVG pairs `scripts/snap-render-ab.py` leaves in `out/snap-render-ab`
and the refit counts in `out/snap-gaps-occt.json`, and reports every part that
comes out of the snap with fewer `<path>` plus `<line>` elements than it went in
with, split by whether pass 2 refitted anything.

A dropped element is what an eyeball pass over a full-frame render misses:
`67887` and `33089` were both recorded as "identical off and on" and both lose
a whole outline. The count costs nothing and does not miss them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELEM = re.compile(r"<(?:path|line)\b")


def elements(path: Path) -> int | None:
    if not path.exists():
        return None
    return len(ELEM.findall(path.read_text()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ab", default=str(ROOT / "out/snap-render-ab.jsonl"))
    ap.add_argument("--pairs", default=str(ROOT / "out/snap-render-ab"))
    ap.add_argument("--gaps", default=str(ROOT / "out/snap-gaps-occt.json"))
    ap.add_argument("--all", action="store_true", help="print every part, not "
                    "just the ones that lose an element")
    args = ap.parse_args()

    gaps = json.loads(Path(args.gaps).read_text())
    rows = gaps["rows"] if isinstance(gaps, dict) and "rows" in gaps else gaps
    refits = {r["part"]: r["refits"] for r in rows}

    pairs = Path(args.pairs)
    alone: list[tuple[str, int, int]] = []
    with_pass2: list[tuple[str, int, int, int]] = []
    n_alone = 0

    for line in Path(args.ab).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if "error" in row:
            continue
        part = row["part"]
        off = elements(pairs / f"{part}.off.svg")
        on = elements(pairs / f"{part}.on.svg")
        if off is None or on is None:
            continue
        n = refits.get(part, 0)
        if n == 0:
            n_alone += 1
        if args.all:
            print(f"{part:<14}{on - off:>+5d} elements   "
                  f"largest {row['largest']:>6,d} px   refits {n}")
        if on - off < 0:
            (alone.append((part, on - off, row["largest"])) if n == 0
             else with_pass2.append((part, on - off, row["largest"], n)))

    print(f"\n{n_alone} parts have zero pass-2 refits; {len(alone)} of them "
          f"lose an element")
    print(f"{'part':<14}{'elements':>9}{'largest':>12}")
    for part, d, largest in sorted(alone, key=lambda r: r[1]):
        print(f"{part:<14}{d:>+9d}{largest:>10,d} px")
    if with_pass2:
        print("\nalso lose an element, but pass 2 refitted them too:")
        for part, d, largest, n in sorted(with_pass2, key=lambda r: r[1]):
            print(f"{part:<14}{d:>+9d}{largest:>10,d} px   refits {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
