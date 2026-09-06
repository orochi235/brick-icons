#!/usr/bin/env python3
"""What the census still owes the corpus, per engine, from the database.

    .venv/bin/python scripts/census-coverage.py
    .venv/bin/python scripts/census-coverage.py --out out/census/todo

Three buckets, and they are three different jobs:

  drawn      a render is on disk and indexed
  redraw     measured fine, no render kept -- a render pass, cost known from
             the part's own recorded timing
  fails      every recorded attempt errored -- an engine fix or a longer cap,
             and nothing says how long these take because none finished

`--out` writes each bucket as a plain list, which is what `--list` takes.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

ENGINES = ("naive", "occt")
# What HEAD gains over the code that recorded these timings. occt's is banded
# by the part's own cost -- the gain falls as parts get more expensive -- from
# the 120-part sample CENSUS-RUN2.md carries; its 120s+ band reuses 60-120s and
# is optimistic by however much that understates. naive gained a flat 1.23x
# over the same span, close to the box's own noise floor, so applying occt's
# curve to it would overstate the saving three-fold.
OCCT_BANDS = ((10, 4.20), (30, 3.47), (60, 3.22), (120, 2.58),
              (float("inf"), 2.58))
NAIVE_SPEEDUP = 1.23


def speedup(secs: float, engine: str) -> float:
    if engine != "occt":
        return NAIVE_SPEEDUP
    return next(f for cap, f in OCCT_BANDS if secs < cap)


def coverage(conn, corpus: list[str], engine: str) -> dict[str, list[str]]:
    drawn = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (f"census-{engine}",))}
    ok, seen = {}, set()
    for r in conn.execute(
            "SELECT part_id, error, secs FROM measurements WHERE engine = ?",
            (engine,)):
        seen.add(r["part_id"])
        # A part measured in any run can be drawn; only one that has never
        # completed is a failure. The archive's rows count for this.
        if r["error"] is None:
            ok[r["part_id"]] = max(ok.get(r["part_id"], 0.0), r["secs"] or 0.0)

    buckets: dict[str, list[str]] = {"drawn": [], "redraw": [],
                                     "fails": [], "unmeasured": []}
    for pid in corpus:
        if pid in drawn:
            buckets["drawn"].append(pid)
        elif pid in ok:
            buckets["redraw"].append(pid)
        elif pid in seen:
            buckets["fails"].append(pid)
        else:
            buckets["unmeasured"].append(pid)
    return buckets, ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--corpus", default=str(ROOT / "out/census/parts.txt"))
    ap.add_argument("--out", help="directory to write <engine>-<bucket>.txt into")
    args = ap.parse_args()

    corpus = [p for p in Path(args.corpus).read_text().split() if p]
    conn = db.connect(args.db)
    print(f"corpus: {len(corpus)} parts\n")
    try:
        for engine in ENGINES:
            buckets, ok = coverage(conn, corpus, engine)
            print(f"{engine}")
            for name in ("drawn", "redraw", "fails", "unmeasured"):
                n = len(buckets[name])
                if not n and name == "unmeasured":
                    continue
                print(f"  {name:<11} {n:>6}  {n / len(corpus) * 100:4.1f}%")

            hours = sum(ok[p] / speedup(ok[p], engine)
                        for p in buckets["redraw"]) / 3600
            if hours:
                print(f"  redraw is about {hours:.1f} core-hours at HEAD's speed")
            # One error per part, from its latest attempt -- a part that failed
            # in several runs has a row in each, and counting rows reports more
            # failures than there are parts.
            failing = set(buckets["fails"])
            latest = {}
            for r in conn.execute(
                    "SELECT part_id, error FROM measurements WHERE engine = ? "
                    "AND error IS NOT NULL ORDER BY run_id", (engine,)):
                if r["part_id"] in failing:
                    latest[r["part_id"]] = r["error"]
            errs = Counter(latest.values())
            if errs:
                print("  " + ", ".join(f"{n} {e}" for e, n in errs.most_common()))
            print()

            if args.out:
                out = Path(args.out)
                out.mkdir(parents=True, exist_ok=True)
                for name in ("redraw", "fails", "unmeasured"):
                    if not buckets[name]:
                        continue
                    path = out / f"{engine}-{name}.txt"
                    path.write_text("\n".join(buckets[name]) + "\n")
                    print(f"  wrote {path} ({len(buckets[name])})")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
