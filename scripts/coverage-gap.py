#!/usr/bin/env python
"""Why the dashboard and the fleet tooling count a slot differently.

Both answer "what does this slot still owe", and they answer it in different
words. `slot-coverage.py` picks the work a job should do; the dashboard's
coverage bars say how far the slot got. Where they disagree, one of them is
asking the fleet for work nothing will ever do -- so the disagreement is the
thing to read, not either number on its own.

Two differences produce nearly all of it:

  out of scope   The dashboard's working set carries the whole library by
                 default, including the `|` categories LDraw marks as parts
                 nobody at LEGO made and the ids on the degenerate list.
                 `slot-coverage.corpus` drops both. They are untried, they
                 will stay untried, and on the bars they are a dark tip no
                 job can clear.

  latest news    The dashboard reads a part by the newest thing that happened
                 to it, so a part drawn in one round and timed out in the next
                 counts as `timeout`. `slot-coverage` counts it drawn: the
                 drawing exists and re-rendering it buys nothing.

  drew nothing   A run that finished clean and produced no drawing reads as
                 untried, because the state is only recorded where the pass
                 left `attempts` rows. Where it did not -- silhouette-naive --
                 the bars ask the fleet for thousands of parts that have
                 already answered.

Run it against a slot or with no argument for every slot.
"""
from __future__ import annotations

import argparse
import importlib.util
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import db  # noqa: E402
from brick_icons.lab import stats  # noqa: E402
from brick_icons.lab.cells import not_applicable  # noqa: E402


def _slot_coverage():
    """`slot-coverage.py` as a module, hyphen and all."""
    path = Path(__file__).resolve().parent / "slot-coverage.py"
    spec = importlib.util.spec_from_file_location("slot_coverage", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["slot_coverage"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="coverage-gap")
    p.add_argument("--db", default=str(db.DEFAULT_PATH))
    p.add_argument("--slot", action="append", help="one slot (repeatable)")
    p.add_argument("--list", metavar="SLOT",
                   help="print one class of part id for this slot")
    p.add_argument("--class", dest="klass", default="scope",
                   choices=("scope", "answered", "left"),
                   help="which class --list prints (default: scope)")
    p.add_argument("--batch", metavar="FILE",
                   help="write --list as a batch file instead: one onto item "
                        "a line, the shape census-batch.sh --each reads")
    p.add_argument("--per-batch", type=int, default=12)
    args = p.parse_args(argv)

    sc = _slot_coverage()
    conn = db.connect(args.db)
    conn.row_factory = sqlite3.Row
    ids, _ = stats.members(conn)
    scope = set(sc.corpus(conn))
    degenerate = sc.degenerate()

    latest: dict[str, dict[str, str]] = {}
    for row in conn.execute(stats._LATEST_ERROR_BY_SOURCE):
        latest.setdefault(row["source"], {})[row["part_id"]] = row["error"]
    drawn: dict[str, set[str]] = {}
    for row in conn.execute("SELECT part_id, source FROM renders"):
        drawn.setdefault(row["source"], set()).add(row["part_id"])
    nothing: dict[str, set[str]] = {}
    for row in conn.execute("SELECT DISTINCT part_id, source FROM attempts "
                            "WHERE state = 'none'"):
        nothing.setdefault(row["source"], set()).add(row["part_id"])
    printed = {r[0] for r in conn.execute("SELECT id FROM parts WHERE printed = 1")}
    obsolete = {r[0] for r in conn.execute("SELECT id FROM parts WHERE obsolete = 1")}
    measured: dict[str, set[str]] = {}
    for row in conn.execute("SELECT DISTINCT part_id, source FROM measurements "
                            "WHERE source IS NOT NULL"):
        measured.setdefault(row["source"], set()).add(row["part_id"])

    slots = args.slot or [s for s in db.SOURCES if s in drawn]
    print(f"working set {len(ids):,} parts; slot-coverage scope {len(scope):,}; "
          f"{len(ids - scope):,} in one and not the other\n")
    print(f"{'slot':18s} {'untried':>8s} {'of scope':>9s} {'answered':>9s} "
          f"{'left':>6s} {'drawn':>7s} {'but news':>9s}")
    for slot in slots:
        have = drawn.get(slot, set())
        told = latest.get(slot, {})
        untried = {p for p in ids - have - told.keys() - nothing.get(slot, set())
                   if not not_applicable(slot, p in printed, False,
                                         p in obsolete)}
        # Measured, so it has answered -- the row simply carries no error and
        # no drawing. `slot-coverage` calls these errored.
        answered = untried & measured.get(slot, set())
        # Drawn, but the newest thing that happened to it was not the drawing,
        # so the bars file it under that instead.
        news = have & told.keys()
        print(f"{slot:18s} {len(untried):8,d} {len(untried - scope):9,d} "
              f"{len(answered):9,d} {len(untried & scope) - len(answered):6,d} "
              f"{len(have):7,d} {len(news):9,d}")

    if args.list:
        slot = args.list
        have, told = drawn.get(slot, set()), latest.get(slot, {})
        untried = {p for p in ids - have - told.keys() - nothing.get(slot, set())
                   if not not_applicable(slot, p in printed, False,
                                         p in obsolete)}
        answered = untried & measured.get(slot, set())
        picked = sorted({"scope": untried - scope,
                         "answered": answered,
                         "left": (untried & scope) - answered}[args.klass])
        if args.batch:
            out = Path(args.batch)
            out.parent.mkdir(parents=True, exist_ok=True)
            lines = [",".join(picked[i:i + args.per_batch])
                     for i in range(0, len(picked), args.per_batch)]
            out.write_text("\n".join(lines) + "\n" if lines else "")
            print(f"\nwrote {out} -- {len(picked)} parts, {len(lines)} batches")
            return 0 if picked else 1
        print(f"\n{len(picked)} {args.klass} in {slot}:")
        for pid in picked:
            row = conn.execute("SELECT category, title FROM parts WHERE id = ?",
                               (pid,)).fetchone()
            why = ("degenerate" if pid in degenerate
                   else f"category {row['category']!r}")
            print(f"  {pid:14s} {why:22s} {row['title'][:44]}")
    print("\n'of scope' can never be rendered and is a permanent dark tip on the "
          "bars.\n'answered' ran and produced no drawing, so asking for it again "
          "buys nothing.\n'left' is work genuinely owed. 'but news' is drawn "
          "parts the bars file under\na later failure.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
