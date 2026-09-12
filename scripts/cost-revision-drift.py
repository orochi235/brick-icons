#!/usr/bin/env python
"""Does a slot cost the same at one engine revision as at another?

The cost panel reads each slot at one revision and throws the rest away, on
the grounds that revisions are not comparable. This asks whether that is true
of the revisions actually in the database.

The naive comparison -- each revision's seconds summed over its own parts,
against the base's -- cannot answer it: two revisions of a slot usually hold
DIFFERENT parts, and a sum over heavier parts moves the ratio with no engine
change at all. silhouette-naive reads 0.98 at one revision and 0.66 at
another, over part sets whose base medians are 1.8s and 4.9s.

Two comparisons answer it, and they are not equal. Where a part was drawn at
both revisions, pair it with itself: that holds the part fixed and leaves
nothing for a mix to move. Where no part overlaps, bin every part by what the
BASE spent on it, take the median per-part ratio inside each bin, and combine
the bins under fixed weights -- weaker, because a bin spans a 2x range of
part weights and a revision can sit low in every one of them.

Trust the paired column wherever it has a number. The two disagree on occt,
where pairs say the revisions are identical and bins say 0.68x.
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import db  # noqa: E402
from brick_icons.lab import stats  # noqa: E402

#: Base-seconds bin edges. A part's own cost spans three orders of magnitude,
#: and a ratio is only meaningful against parts of comparable weight.
EDGES = (0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, float("inf"))
#: Below this a bin's median is noise rather than a measurement.
FLOOR = 25


def binned(secs: dict[str, float], base: dict[str, float]) -> dict[int, list[float]]:
    """Per-part ratios against the base, grouped by the base's own seconds."""
    out: dict[int, list[float]] = {}
    for part, s in secs.items():
        b = base.get(part)
        if not b:
            continue
        i = max(i for i, lo in enumerate(EDGES) if b >= lo)
        out.setdefault(i, []).append(s / b)
    return out


def drift(a: dict[str, float], b: dict[str, float],
          base: dict[str, float]) -> tuple[float | None, int]:
    """How much dearer `b` is than `a`, over parts of matched weight.

    None where no bin holds enough of both to say -- which is an answer, not a
    failure: it means these two revisions cannot be compared at all.
    """
    ba, bb = binned(a, base), binned(b, base)
    shared = [i for i in ba if i in bb
              and len(ba[i]) >= FLOOR and len(bb[i]) >= FLOOR]
    if not shared:
        return None, 0
    weight = sum(len(ba[i]) + len(bb[i]) for i in shared)
    gap = sum((len(ba[i]) + len(bb[i])) * (st.median(bb[i]) / st.median(ba[i]))
              for i in shared if st.median(ba[i]))
    return gap / weight, weight


#: Every silhouette-naive row ever taken, not just each part's latest, which
#: is what `_cost_rows` returns -- a part drawn at two revisions is invisible
#: to the panel's own query and is exactly what the paired test needs.
_EVERY_ROW = """
SELECT part_id, source, build, secs FROM measurements
WHERE secs IS NOT NULL AND source IS NOT NULL AND build IS NOT NULL
"""


def paired(conn, source: str, a: str, b: str) -> tuple[float | None, int]:
    """How much dearer `b` is than `a` over the parts drawn at both."""
    rows: dict[str, dict[str, list[float]]] = {}
    for row in conn.execute(_EVERY_ROW):
        if row["source"] == source and row["build"] in (a, b):
            rows.setdefault(row["build"], {}).setdefault(
                row["part_id"], []).append(row["secs"])
    here, there = rows.get(a, {}), rows.get(b, {})
    both = [p for p in here if p in there]
    if len(both) < FLOOR:
        return None, len(both)
    return st.median(st.median(there[p]) / st.median(here[p])
                     for p in both), len(both)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cost-revision-drift")
    p.add_argument("--db", default=str(db.DEFAULT_PATH))
    p.add_argument("--min", type=int, default=100,
                   help="skip a revision holding fewer parts than this")
    args = p.parse_args(argv)

    conn = db.connect(args.db)
    conn.row_factory = sqlite3.Row
    ids = {r[0] for r in conn.execute("SELECT DISTINCT part_id FROM measurements")}
    at: dict[str, dict[str, dict[str, float]]] = {}
    for row in stats._cost_rows(conn):
        if row["part_id"] in ids and row["build"]:
            at.setdefault(row["source"], {}).setdefault(
                row["build"], {})[row["part_id"]] = row["secs"]

    plain = [s for s in at if s == stats.engine_for(s)]
    base_slot = max(plain or list(at),
                    key=lambda s: max(len(by) for by in at[s].values()))
    base = max(at[base_slot].values(), key=len)
    print(f"base {base_slot} over {len(base):,} parts; "
          f"per-part ratios binned by base seconds {EDGES[1:-1]}\n")

    print(f"{'slot':18s} {'revision':17s} {'parts':>6s} {'sum-ratio':>9s} "
          f"{'paired':>7s} {'n':>6s} {'binned':>7s} {'n':>6s}")
    for source in sorted(at):
        revs = sorted(at[source], key=lambda b: -len(at[source][b]))
        widest = at[source][revs[0]]
        for rev in revs:
            secs = at[source][rev]
            if len(secs) < args.min:
                continue
            common = set(secs) & set(base)
            ratio = (sum(secs[p] for p in common) / sum(base[p] for p in common)
                     if common else float("nan"))
            if rev == revs[0]:
                print(f"{source:18s} {rev:17s} {len(secs):6,d} {ratio:9.3f} "
                      f"{'widest':>7s}")
                continue
            pair, pn = paired(conn, source, revs[0], rev)
            gap, n = drift(widest, secs, base)
            say = lambda v: "--" if v is None else f"{v:.2f}x"  # noqa: E731
            print(f"{source:18s} {rev:17s} {len(secs):6,d} {ratio:9.3f} "
                  f"{say(pair):>7s} {pn:6,d} {say(gap):>7s} {n:6,d}")
    print("\nBoth columns are the gap against the slot's widest revision, over "
          "the parts each can\ncompare. 'paired' holds the part fixed and is "
          "the one to read; 'binned' only holds its\nweight class, and reads "
          "a revision sitting low within its bins as a cheaper engine.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
