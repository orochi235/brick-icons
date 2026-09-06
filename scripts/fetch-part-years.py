#!/usr/bin/env python3
"""Derive each part's production years and set count from Rebrickable's dumps.

    .venv/bin/python scripts/fetch-part-years.py
    .venv/bin/python scripts/fetch-part-years.py --db corpus.db

Rebrickable publishes no per-part years; what it publishes is which set holds
which part, and what year each set is from. A part's first and last year are
the first and last year of the sets it appears in, and how many sets that is
says how common the part is -- the three numbers the wall's `retired`,
`popular` and `obscure` tags are made of.

The dumps are public and need no key. They are cached under `out/rebrickable`
and reused; pass `--refresh` to pull them again.

Writes `tests/goldens/part-years.csv`, which is committed: it is 24k small
rows, and regenerating it otherwise means another 15MB of downloads. Also
writes the rows straight into `corpus.db`, so a live wall picks them up
without a rebuild.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

BASE = "https://cdn.rebrickable.com/media/downloads"
DUMPS = ("parts", "sets", "inventories", "inventory_parts",
         "part_relationships")
DEFAULT_CACHE = Path("out") / "rebrickable"
DEFAULT_OUT = Path("tests") / "goldens" / "part-years.csv"
DEFAULT_SUCCESSORS = Path("tests") / "goldens" / "part-successors.csv"

#: Relation types that can name a replacement, best first. A mould is a
#: re-cut of the same part; an alternate merely fits the same hole, which
#: is why it loses -- 2780's alternate is the frictionless pin 3673, and
#: its mould is 61332, the part that actually replaced it.
SUCCESSOR_RELS = ("M", "A")

# A printed part's decoration suffix -- `4740p03` is drawn from `4740`, and
# Rebrickable numbers the print differently or not at all, so the base part's
# years are the best answer available for it.
_PRINT_SUFFIX = re.compile(r"^(\d{3,}[a-z]?)(p[0-9a-z]+|pr\d+)$")


def fetch(name: str, cache: Path, refresh: bool) -> Path:
    path = cache / f"{name}.csv.gz"
    if path.is_file() and not refresh:
        print(f"  {name}: cached ({path.stat().st_size:,} bytes)", flush=True)
        return path
    cache.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{name}.csv.gz"
    print(f"  {name}: fetching {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "brick-icons"})
    with urllib.request.urlopen(req, timeout=120) as r:
        path.write_bytes(r.read())
    print(f"  {name}: {path.stat().st_size:,} bytes", flush=True)
    return path


def rows(path: Path):
    with gzip.open(path, "rb") as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8"))


def part_facts(cache: Path) -> dict[str, tuple[int, int, int]]:
    """(first year, last year, set count) per Rebrickable part number."""
    set_year = {r["set_num"]: int(r["year"]) for r in rows(cache / "sets.csv.gz")
                if r["year"]}
    print(f"  {len(set_year):,} sets", flush=True)
    # Version 1 only: later versions are the same set re-inventoried, and
    # counting them would inflate how common a part looks.
    inventory_set = {r["id"]: r["set_num"] for r in rows(cache / "inventories.csv.gz")
                     if r["version"] == "1"}
    print(f"  {len(inventory_set):,} first-version inventories", flush=True)

    sets_with: dict[str, set[str]] = defaultdict(set)
    for i, r in enumerate(rows(cache / "inventory_parts.csv.gz"), 1):
        if i % 500_000 == 0:
            print(f"  inventory_parts: {i:,} rows", flush=True)
        set_num = inventory_set.get(r["inventory_id"])
        if set_num is not None and set_num in set_year:
            sets_with[r["part_num"]].add(set_num)
    print(f"  {len(sets_with):,} parts appear in a set", flush=True)

    out = {}
    for part_num, in_sets in sets_with.items():
        years = [set_year[s] for s in in_sets]
        out[part_num] = (min(years), max(years), len(in_sets))
    return out


def match(part_id: str, facts: dict[str, tuple[int, int, int]]) -> tuple[str, str] | None:
    """The Rebrickable number to read `part_id`'s years off, and how it matched."""
    if part_id in facts:
        return part_id, "exact"
    printed = _PRINT_SUFFIX.match(part_id)
    if printed and printed.group(1) in facts:
        return printed.group(1), "base"
    return None


def successors(cache: Path, facts: dict[str, tuple[int, int, int]],
               ids: set[str]) -> dict[str, tuple[str, str]]:
    """The part that replaced each one, where Rebrickable records a partner
    still being made after it stopped.

    Direction is taken from the years rather than from the row: the dump's
    child/parent columns do not consistently put the newer part on one side.
    """
    adjacent: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    kept = 0
    for r in rows(cache / "part_relationships.csv.gz"):
        rel = r["rel_type"]
        if rel not in SUCCESSOR_RELS:
            continue
        a, b = r["child_part_num"], r["parent_part_num"]
        adjacent[a][rel].add(b)
        adjacent[b][rel].add(a)
        kept += 1
    print(f"  {kept:,} mould and alternate relations", flush=True)

    out: dict[str, tuple[str, str]] = {}
    for part_id in sorted(ids):
        if part_id not in facts:
            continue
        _, last, _ = facts[part_id]
        for rel in SUCCESSOR_RELS:
            best = None
            for other in adjacent[part_id][rel]:
                if other not in ids or other not in facts:
                    continue
                if facts[other][1] <= last:
                    continue
                if best is None or facts[other][1:] > facts[best][1:]:
                    best = other
            if best is not None:
                out[part_id] = (best, rel)
                break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--cache", default=str(ROOT / DEFAULT_CACHE))
    ap.add_argument("--out", default=str(ROOT / DEFAULT_OUT))
    ap.add_argument("--successors-out", default=str(ROOT / DEFAULT_SUCCESSORS))
    ap.add_argument("--refresh", action="store_true",
                    help="pull the dumps again instead of using the cache")
    args = ap.parse_args()

    cache = Path(args.cache)
    print(f"{len(DUMPS)} dump(s)", flush=True)
    for name in DUMPS:
        fetch(name, cache, args.refresh)

    facts = part_facts(cache)

    conn = db.connect(args.db)
    try:
        ids = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    finally:
        conn.close()
    print(f"{len(ids):,} parts in the corpus", flush=True)

    matched = []
    for i, part_id in enumerate(ids, 1):
        if i % 5000 == 0:
            print(f"  matched {i:,}/{len(ids):,}", flush=True)
        hit = match(part_id, facts)
        if hit is None:
            continue
        part_num, how = hit
        first, last, sets = facts[part_num]
        matched.append((part_id, first, last, sets, how))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "year_from", "year_to", "sets", "matched"])
        w.writerows(matched)
    exact = sum(1 for m in matched if m[4] == "exact")
    print(f"wrote {out}: {len(matched):,} of {len(ids):,} parts "
          f"({exact:,} exact, {len(matched) - exact:,} via base part)", flush=True)

    found = successors(cache, facts, set(ids))
    succ_out = Path(args.successors_out)
    with succ_out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "successor", "rel"])
        w.writerows((p, s, r) for p, (s, r) in sorted(found.items()))
    moulds = sum(1 for s, r in found.values() if r == "M")
    print(f"wrote {succ_out}: {len(found):,} successors "
          f"({moulds:,} by mould, {len(found) - moulds:,} by alternate)", flush=True)

    conn = db.connect(args.db)
    try:
        n = db.import_part_years(conn, out)
        m = db.import_part_successors(conn, succ_out)
    finally:
        conn.close()
    print(f"loaded {n:,} year rows and {m:,} successors into {args.db}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
