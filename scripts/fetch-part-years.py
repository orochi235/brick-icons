#!/usr/bin/env python3
"""Derive each part's production years and set count from Rebrickable's dumps.

    .venv/bin/python scripts/fetch-part-years.py
    .venv/bin/python scripts/fetch-part-years.py --db corpus.db

Rebrickable publishes no per-part years; what it publishes is which set holds
which part, and what year each set is from. A part's first and last year are
the first and last year of the sets it appears in, and how many sets that is
says how common the part is -- the three numbers the wall's `retired`,
`popular` and `obscure` tags are made of. Each of those rows also names a
color, so the same walk counts how many colors a part was made in.

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
         "part_relationships", "elements")
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

# A sticker's own id is the sheet number plus a letter -- `003238a` is one
# sticker off sheet `003238`, and the sheet is what Rebrickable inventories.
_STICKER = re.compile(r"^(\d+)[a-z]+$")

#: LDraw names the sets a part was made for in its `!KEYWORDS` line, with or
#: without the variant suffix: "set 375-2", "Set 1620-2", "set 6075".
_KW_LINE = re.compile(r"^0\s+!KEYWORDS\s+(.*)$", re.IGNORECASE)
_KW_SET = re.compile(r"\bset\s+(\d{2,7}(?:-\d+)?)\b", re.IGNORECASE)


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


def part_facts(cache: Path) -> dict[str, tuple[int, int, int, int]]:
    """(first year, last year, set count, color count) per Rebrickable part."""
    set_year = {r["set_num"]: int(r["year"]) for r in rows(cache / "sets.csv.gz")
                if r["year"]}
    print(f"  {len(set_year):,} sets", flush=True)
    # Version 1 only: later versions are the same set re-inventoried, and
    # counting them would inflate how common a part looks.
    inventory_set = {r["id"]: r["set_num"] for r in rows(cache / "inventories.csv.gz")
                     if r["version"] == "1"}
    print(f"  {len(inventory_set):,} first-version inventories", flush=True)

    sets_with: dict[str, set[str]] = defaultdict(set)
    colors_of: dict[str, set[str]] = defaultdict(set)
    for i, r in enumerate(rows(cache / "inventory_parts.csv.gz"), 1):
        if i % 500_000 == 0:
            print(f"  inventory_parts: {i:,} rows", flush=True)
        set_num = inventory_set.get(r["inventory_id"])
        if set_num is not None and set_num in set_year:
            sets_with[r["part_num"]].add(set_num)
            colors_of[r["part_num"]].add(r["color_id"])
    print(f"  {len(sets_with):,} parts appear in a set", flush=True)

    out = {}
    for part_num, in_sets in sets_with.items():
        years = [set_year[s] for s in in_sets]
        out[part_num] = (min(years), max(years), len(in_sets),
                         len(colors_of[part_num]))
    return out


def design_index(cache: Path) -> dict[str, set[str]]:
    """LEGO design number -> the Rebrickable parts made from that mould.

    LDraw names modern parts by their LEGO design number, which is not what
    Rebrickable numbers them by; `elements.csv` is the only dump that carries
    both. Worth about 2,000 parts that match no other way.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows(cache / "elements.csv.gz"):
        design = (r.get("design_id") or "").strip()
        if design:
            out[design].add(r["part_num"])
    print(f"  {len(out):,} design ids", flush=True)
    return out


def match(part_id: str, facts: dict[str, tuple[int, int, int, int]],
          designs: dict[str, set[str]]) -> tuple[set[str], str] | None:
    """The Rebrickable numbers to read `part_id`'s years off, and how they
    matched. A set rather than one number: a design id names every mould cut
    from it, and the part's span is the span of all of them."""
    if part_id in facts:
        return {part_id}, "exact"
    printed = _PRINT_SUFFIX.match(part_id)
    if printed and printed.group(1) in facts:
        return {printed.group(1)}, "base"
    sticker = _STICKER.match(part_id)
    if sticker and sticker.group(1) in facts:
        return {sticker.group(1)}, "sheet"
    for candidate in (part_id, printed.group(1) if printed else None):
        if candidate and candidate in designs:
            hits = {q for q in designs[candidate] if q in facts}
            if hits:
                return hits, "design"
    return None


def keyword_years(dat: Path, set_year: dict[str, int],
                  bare: dict[str, list[int]]) -> tuple[int, int] | None:
    """The years of the sets LDraw's own `!KEYWORDS` line names, if any.

    An estimate, and only ever a fallback: keywords name a couple of
    illustrative sets rather than an inventory, so for a part in hundreds of
    sets the earliest named is nowhere near the earliest. Measured against the
    inventory years we already trust, the error tracks how many sets a part is
    in -- a median of one year at 1-2 sets, fourteen at over a hundred. Every
    part reaching this route is absent from every inventory, which is the
    regime where it holds up; stickers checked at 95% exact.
    """
    if not dat.is_file():
        return None
    named: list[str] = []
    for line in dat.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("0 "):
            break          # past the header; the geometry starts here
        found = _KW_LINE.match(stripped)
        if found:
            named.append(found.group(1))
    if not named:
        return None
    years: list[int] = []
    for ref in _KW_SET.findall(" ; ".join(named)):
        if ref in set_year:
            years.append(set_year[ref])
        else:
            years.extend(bare.get(ref.split("-")[0], ()))
    return (min(years), max(years)) if years else None


def successors(cache: Path, facts: dict[str, tuple[int, int, int, int]],
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
        _, last, _, _ = facts[part_id]
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
    ap.add_argument("--ldraw-dir", default=str(ROOT / "vendor" / "ldraw"),
                    help="the library to read `!KEYWORDS` set references from")
    ap.add_argument("--refresh", action="store_true",
                    help="pull the dumps again instead of using the cache")
    args = ap.parse_args()

    cache = Path(args.cache)
    print(f"{len(DUMPS)} dump(s)", flush=True)
    for name in DUMPS:
        fetch(name, cache, args.refresh)

    facts = part_facts(cache)
    designs = design_index(cache)
    set_year = {r["set_num"]: int(r["year"])
                for r in rows(cache / "sets.csv.gz") if r["year"]}
    bare: dict[str, list[int]] = defaultdict(list)
    for set_num, year in set_year.items():
        bare[set_num.split("-")[0]].append(year)

    conn = db.connect(args.db)
    try:
        ids = [r["id"] for r in conn.execute("SELECT id FROM parts ORDER BY id")]
    finally:
        conn.close()
    print(f"{len(ids):,} parts in the corpus", flush=True)

    parts_dir = Path(args.ldraw_dir) / "parts"
    matched = []
    for i, part_id in enumerate(ids, 1):
        if i % 5000 == 0:
            print(f"  matched {i:,}/{len(ids):,}", flush=True)
        hit = match(part_id, facts, designs)
        if hit is not None:
            part_nums, how = hit
            spans = [facts[n] for n in part_nums]
            # A design id can name several moulds. The span is all of them;
            # the counts are the largest single mould's, because summing them
            # would count one set once per mould cut from it.
            best = max(spans, key=lambda s: s[2])
            matched.append((part_id, min(s[0] for s in spans),
                            max(s[1] for s in spans), best[2], how, best[3]))
            continue
        # Nothing in any inventory. LDraw's own keywords are the last resort,
        # and the row is marked so the wall can tell an estimate from a count:
        # `sets` and `colors` stay 0 because there is no inventory behind them,
        # which is also why `cells` must not read a popularity out of them.
        span = keyword_years(parts_dir / f"{part_id}.dat", set_year, bare)
        if span is not None:
            matched.append((part_id, span[0], span[1], 0, "keywords", 0))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "year_from", "year_to", "sets", "matched",
                    "colors"])
        w.writerows(matched)
    by_route: dict[str, int] = defaultdict(int)
    for m in matched:
        by_route[m[4]] += 1
    routes = ", ".join(f"{n:,} {route}" for route, n in sorted(
        by_route.items(), key=lambda kv: -kv[1]))
    print(f"wrote {out}: {len(matched):,} of {len(ids):,} parts ({routes})",
          flush=True)

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
