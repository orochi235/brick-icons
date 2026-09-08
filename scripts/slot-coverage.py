#!/usr/bin/env python3
"""What each render slot still owes the corpus, and a batch list to fill it.

    .venv/bin/python scripts/slot-coverage.py
    .venv/bin/python scripts/slot-coverage.py --slot white-occt --budget 4

`census-coverage.py` answers the same question for the census's own facets,
read through `measurements`. This one reads `renders`: a slot is short a part
when no row files a drawing under it, whatever any measurement says.

The corpus is every non-obsolete part outside `db.OUT_OF_SCOPE_CATEGORIES`,
less the parts that take a node down rather than failing.

**A slot's flags are derived, never listed here.** Each comes from
`db._CANONICAL` resolved through the CLI's own parser, so a slot added there
is renderable by this script with no edit, and a slot whose canonical drawing
changes cannot go on being filled at the old config.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, db  # noqa: E402

DEGENERATE = ROOT / "tests" / "goldens" / "degenerate-parts.toml"

#: Slots this script cannot fill, and why. `compare-silhouette-truth.py` draws
#: through `cli.process_one` with the outline engine, so a slot whose drawing
#: comes from somewhere else is not a batch anyone can launch from here.
UNFILLABLE = {
    "ldview": "LDView renders it; scripts/ldview-batch.py",
    "reference": "a browser renders it; scripts/shot-sink.py",
}

#: Why the estimate is a floor and not a forecast: it is built from the parts
#: the slot has ALREADY drawn, and those are the ones that were cheap enough
#: to finish. What is left over-represents whatever was slow or failed --
#: printed parts, mostly -- so the true mean of the remainder is higher than
#: the mean of the history, and nothing here can see by how much.

#: How much of a part's recorded cost a fresh pass pays. The census row times
#: the whole oracle -- render, rasterize, truth mask, compare -- and a fill
#: pass runs exactly that, so the figure transfers as it stands. It is a
#: budget, not a promise: an engine change moves it and nothing says so.
#:
#: Reached only by a slot whose engine has never been measured at all. A slot
#: with no history of its own borrows its engine's other slots instead --
#: geometry dominates the cost, and those rows drew the same parts with the
#: same engine.
FALLBACK_SECS = 25.0


def degenerate() -> set[str]:
    if not DEGENERATE.is_file():
        return set()
    with DEGENERATE.open("rb") as fh:
        return {e["id"] for e in tomllib.load(fh).get("part", [])}


#: A slot whose corpus is narrower than the library's, as an extra WHERE
#: clause. The decal slot draws decoration, so a plain brick is not missing
#: from it -- scoring it against the whole library would leave it reported
#: 12,000 parts short of a coverage it can never reach.
SLOT_SCOPE = {"decal": "(printed = 1 OR category = 'Sticker')"}


def corpus(conn, slot: str | None = None) -> list[str]:
    """Every part in scope for a slot, id order. Slotless: the whole library."""
    marks = ",".join("?" * len(db.OUT_OF_SCOPE_CATEGORIES))
    bad = degenerate()
    narrow = SLOT_SCOPE.get(slot or "")
    extra = f"AND {narrow} " if narrow else ""
    return [r["id"] for r in conn.execute(
        f"SELECT id FROM parts WHERE obsolete = 0 "
        f"AND (category IS NULL OR category NOT IN ({marks})) {extra}"
        f"ORDER BY id",
        db.OUT_OF_SCOPE_CATEGORIES) if r["id"] not in bad]


def flags_for(slot: str) -> dict:
    """The census pass's arguments for this slot, out of its canonical argv.

    Resolved through the parser rather than read off the list: `occt` states
    no stroke width and inherits 2/2 from the config, where the census pass
    would default it to 0 and quietly draw a different slot's picture.
    """
    parsed = cli.build_parser().parse_args(db.canonical_argv("3001", slot))
    cfg = cli._config_from_args(parsed)
    if cfg.decal:
        # A decal has no viewpoint, no engine and no strokes. Handing the
        # batch the census pass's drawing flags would draw a silhouette into
        # the decal slot, which is a wrong picture rather than an error.
        return {"engine": cfg.engine, "extra": "--decal"}
    extra = ["--shade-style", cfg.shade_style,
             "--line-width", str(cfg.line_width),
             "--silhouette-width", str(cfg.silhouette_width)]
    if cfg.opacity is not None and cfg.opacity != 1.0:
        extra += ["--opacity", str(cfg.opacity)]
    return {"engine": cfg.engine, "extra": " ".join(extra)}


def owed(conn, slot: str, scope: list[str]) -> dict:
    """The slot's parts split by how much is known about each.

    The per-part figure is the MEAN, not the median. Render cost is savagely
    skewed -- a measured white-occt round came in at a 2.7s median against a
    26.4s mean, p99 223s -- and a total is n times the mean. Budgeting on the
    median underestimated a 12,987-part round as 4.2h when it was closer to
    12h.

    `never` before `errored`, which is the order a run cut short by its
    deadline should spend its time in: a part that timed out costs its whole
    cap and yields nothing.
    """
    drawn = {r["part_id"] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = ?", (slot,))}
    tried, cost = {}, []
    for r in conn.execute(
            "SELECT part_id, error, secs FROM measurements WHERE source = ?",
            (slot,)):
        if r["error"] is None and r["secs"]:
            cost.append(r["secs"])
        # A part that ever completed is not an "errored" one, whatever a
        # later run recorded: the run it completed in proves it can be drawn.
        tried[r["part_id"]] = tried.get(r["part_id"], False) or r["error"] is None

    engine = slot.rsplit("-", 1)[-1]
    borrowed = False
    if cost:
        median = statistics.mean(cost)
    else:
        peers = [r["secs"] for r in conn.execute(
            "SELECT secs FROM measurements WHERE engine = ? AND error IS NULL "
            "AND secs IS NOT NULL", (engine,))]
        median = statistics.mean(peers) if peers else FALLBACK_SECS
        # "borrowed" and "guessed" are different claims and a budget built on
        # the second is worth much less. A slot whose engine has no rows at
        # all got FALLBACK_SECS, and must not report it as measurement.
        borrowed = "engine" if peers else "fallback"

    out = {"drawn": [], "never": [], "errored": [], "median": median,
           "borrowed": borrowed, "secs": {}}
    for pid in scope:
        if pid in drawn:
            out["drawn"].append(pid)
        elif pid not in tried:
            out["never"].append(pid)
        else:
            out["errored"].append(pid)
    for r in conn.execute(
            "SELECT part_id, MAX(secs) s FROM measurements WHERE source = ? "
            "AND error IS NULL GROUP BY part_id", (slot,)):
        out["secs"][r["part_id"]] = r["s"]
    return out


def batch(owed_: dict, budget_secs: float) -> list[str]:
    """As many owed parts as fit the budget, cheapest information first."""
    picked, spent = [], 0.0
    for pid in owed_["never"] + owed_["errored"]:
        c = owed_["secs"].get(pid) or owed_["median"]
        if picked and spent + c > budget_secs:
            break
        picked.append(pid)
        spent += c
    return picked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--slot", help="write a batch list for this slot")
    ap.add_argument("--budget", type=float, default=4.0,
                    help="wall-clock hours the batch should fill (default 4)")
    ap.add_argument("--workers", type=int, default=10,
                    help="workers the job will run, for the core-hour sum")
    ap.add_argument("--per-batch", type=int, default=12,
                    help="parts per line; a line is one onto item")
    ap.add_argument("--out", help="write the batch lines here")
    args = ap.parse_args()

    conn = db.connect(args.db)
    scope = corpus(conn)
    print(f"corpus: {len(scope)} parts in scope\n", flush=True)

    if not args.slot:
        rows = []
        for slot in db.SOURCES:
            o = owed(conn, slot, corpus(conn, slot))
            rows.append((slot, len(o["drawn"]),
                         len(o["never"]) + len(o["errored"]), o["median"],
                         o["borrowed"]))
        # Emptiest first: the question this table answers is what to fill next.
        for slot, have, miss, med, borrowed in sorted(rows, key=lambda r: -r[2]):
            why = UNFILLABLE.get(slot, "")
            note = f"  {why}" if why else ("" if miss else "  full")
            # A borrowed median is the engine's, not this slot's. Marked
            # because a budget built on one is an estimate of an estimate.
            mark = "~" if borrowed else " "
            print(f"  {slot:<18} have {have:6}  missing {miss:6}"
                  f"  median {mark}{med:5.1f}s{note}", flush=True)
        print("\n  naive slots are low priority; occt is the focus.", flush=True)
        return 0

    if args.slot not in db.SOURCES:
        ap.error(f"unknown slot {args.slot!r}; one of {', '.join(db.SOURCES)}")
    if args.slot in UNFILLABLE:
        ap.error(f"{args.slot} cannot be filled from here: "
                 f"{UNFILLABLE[args.slot]}")

    o = owed(conn, args.slot, corpus(conn, args.slot))
    flags = flags_for(args.slot)
    picked = batch(o, args.budget * args.workers * 3600)
    spent = sum(o["secs"].get(p) or o["median"] for p in picked)

    print(f"{args.slot}", flush=True)
    print(f"  drawn      {len(o['drawn']):6}", flush=True)
    print(f"  never      {len(o['never']):6}", flush=True)
    print(f"  errored    {len(o['errored']):6}", flush=True)
    origin = {"engine": f"borrowed from every {flags['engine']} row",
              "fallback": f"nothing measured yet; the {FALLBACK_SECS:.0f}s "
                          f"default"}.get(o["borrowed"], "this slot's own rows")
    print(f"  mean       {o['median']:6.1f}s per part  ({origin})", flush=True)
    print(f"\n  batch of {len(picked)}: about {spent / 3600:5.1f} core-hours, "
          f"{spent / 3600 / args.workers:5.1f}h on {args.workers} workers",
          flush=True)

    if args.out:
        lines = [",".join(picked[i:i + args.per_batch])
                 for i in range(0, len(picked), args.per_batch)]
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n")
        print(f"  wrote {out} ({len(lines)} batches)", flush=True)
        print(f"\n  ENGINE={flags['engine']}", flush=True)
        print(f"  SOURCE={args.slot}", flush=True)
        print(f"  EXTRA='{flags['extra']}'", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
