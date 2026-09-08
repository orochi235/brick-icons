#!/usr/bin/env python3
"""Write the census corpus -- which parts a sweep covers -- from the database.

    .venv/bin/python scripts/census-scope.py --out out/census/parts.txt

The corpus excludes obsolete parts, and nothing else. A superseded mould is a
part no icon will ever be asked for, so measuring it buys nothing; a printed
part is one the engine is expected to draw.

Printed parts were excluded too, on the rule that they were "out of the engine
loop until the decal work is picked up". That work is picked up -- decoration
goes through `_with_decoration` on the occt path, stickers have been censused,
and the paint-order defect that motivated this scope change was a printed part.
The exclusion was hiding 12,964 parts from every coverage number.

Ordering matters as much as membership, and is the reason this is a script
rather than a query someone retypes: **never tried outranks previously
errored.** A part that timed out costs its whole cap and yields nothing, so a
run cut short by its deadline should spend that time on parts that might
succeed. Sorting by id would interleave them.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

BUCKETS = ("drawn", "never", "errored")
DEGENERATE = ROOT / "tests" / "goldens" / "degenerate-parts.toml"


def degenerate() -> set[str]:
    """Parts that take the node down rather than failing. Excluded by default:
    the per-part memory cap cannot save a machine that stops scheduling."""
    if not DEGENERATE.is_file():
        return set()
    with DEGENERATE.open("rb") as fh:
        return {e["id"] for e in tomllib.load(fh).get("part", [])}


def scope(conn, engine: str) -> dict[str, list[str]]:
    """The corpus in three buckets, in the order a sweep should run them."""
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM parts WHERE obsolete = 0 ORDER BY id")]
    state = {}
    for pid, err in conn.execute(
            "WITH latest AS (SELECT part_id, error, ROW_NUMBER() OVER "
            "  (PARTITION BY part_id ORDER BY rowid DESC) rn "
            " FROM measurements WHERE engine = ?) "
            "SELECT part_id, error FROM latest WHERE rn = 1", (engine,)):
        state[pid] = "drawn" if not err else "errored"
    out = {b: [] for b in BUCKETS}
    for pid in ids:
        out[state.get(pid, "never")].append(pid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--engine", default="occt",
                    help="whose past results order the buckets")
    ap.add_argument("--out", default="out/census/parts.txt")
    ap.add_argument("--batches", help="also write <n>-part batch lines here")
    ap.add_argument("--per-batch", type=int, default=12)
    ap.add_argument("--only", choices=BUCKETS, action="append",
                    help="keep just these buckets (repeatable)")
    ap.add_argument("--include-degenerate", action="store_true",
                    help="put the node-killers back in; see "
                         "tests/goldens/degenerate-parts.toml")
    args = ap.parse_args()

    with db.connect(args.db) as conn:
        buckets = scope(conn, args.engine)
    keep = args.only or list(BUCKETS)
    ids = [pid for b in BUCKETS if b in keep for pid in buckets[b]]
    if not args.include_degenerate:
        bad = degenerate()
        dropped = [p for p in ids if p in bad]
        ids = [p for p in ids if p not in bad]
        if dropped:
            print(f"  degenerate {len(dropped):5}  (dropped: "
                  f"{', '.join(dropped[:6])})", flush=True)

    for b in BUCKETS:
        mark = "" if b in keep else "  (dropped)"
        print(f"  {b:8} {len(buckets[b]):6}{mark}", flush=True)
    print(f"  {'total':8} {len(ids):6}", flush=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(ids) + "\n")
    print(f"wrote {out}", flush=True)
    if args.batches:
        lines = [",".join(ids[i:i + args.per_batch])
                 for i in range(0, len(ids), args.per_batch)]
        Path(args.batches).write_text("\n".join(lines) + "\n")
        print(f"wrote {args.batches} ({len(lines)} batches)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
