#!/usr/bin/env python3
"""Sample the candidate pool the extraction corpus is filtered from.

    python scripts/select-decal-candidates.py --out tests/goldens/decal-candidates.txt

The pool was previously the first N printed parts in sorted order, which is a
prefix of the id space rather than a sample of it: every id began 00-15 and the
library's largest printed families were absent entirely, so the corpus held no
classic brick, plate or tile.

A systematic every-Nth pass over all printed parts fixes that. It is
deterministic, needs no seed, and keeps the library's own proportions — a shape
carrying many prints contributes many rows, which is wanted: repetition of a
common shape is coverage, not waste. What does not belong is a part no engine
could extract from, and `select-decal-corpus.py` drops those downstream.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

PARTS = ROOT / "vendor" / "ldraw" / "parts"


def printed_ids():
    """Parts carrying geometry in a colour other than 16/24."""
    ids = []
    for f in sorted(PARTS.glob("*.dat")):
        try:
            txt = f.read_text(errors="replace")
        except OSError:
            continue
        for ln in txt.splitlines():
            tok = ln.split()
            if (len(tok) > 2 and tok[0] in ("1", "3", "4")
                    and tok[1].isdigit() and int(tok[1]) not in (16, 24)):
                ids.append(f.stem)
                break
    return ids


def sample(ids, n):
    """Every-Nth pick across the whole sorted list, endpoints included."""
    if n >= len(ids):
        return list(ids)
    step = len(ids) / n
    return [ids[min(int(i * step), len(ids) - 1)] for i in range(n)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=600)
    ap.add_argument("--out", default=str(ROOT / "tests" / "goldens"
                                        / "decal-candidates.txt"))
    a = ap.parse_args(argv)

    ids = printed_ids()
    print(f"{len(ids)} printed parts in the library", flush=True)
    picked = sample(ids, a.count)
    shapes = {p.split("p")[0] for p in picked}
    print(f"sampled {len(picked)} across {len(shapes)} base shapes", flush=True)

    header = (
        f"# Candidate pool for the extraction corpus: {len(picked)} parts\n"
        f"# sampled every-Nth across all {len(ids)} printed parts (colour\n"
        f"# other than 16/24), so the pool spans the id space instead of a\n"
        f"# prefix of it. Regenerate with select-decal-candidates.py;\n"
        f"# select-decal-corpus.py filters this to parts a decal can be got\n"
        f"# off. Generated - do not edit.\n")
    Path(a.out).write_text(header + "".join(f"{p}\n" for p in picked))
    print(f"wrote {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
