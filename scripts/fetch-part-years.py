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

# A printed part's decoration suffix -- `4740p03` is drawn from `4740`. The
# base part's years are a last resort for a print, not a good answer: see
# keyword_parts() for the id that actually names it.
_PRINT_SUFFIX = re.compile(r"^(\d{3,}[a-z]?)(p[0-9a-z]+|pr\d+)$")

# A sticker's own id is the sheet number plus a letter -- `003238a` is one
# sticker off sheet `003238`, and the sheet is what Rebrickable inventories.
_STICKER = re.compile(r"^(\d+)[a-z]+$")

#: LDraw names the sets a part was made for in its `!KEYWORDS` line, with or
#: without the variant suffix: "set 375-2", "Set 1620-2", "set 6075".
_KW_LINE = re.compile(r"^0\s+!KEYWORDS\s+(.*)$", re.IGNORECASE)
_KW_SET = re.compile(r"\bset\s+(\d{2,7}(?:-\d+)?)\b", re.IGNORECASE)

#: The same line names the part in the two big catalogs: "BrickLink 3005pb031,
#: Rebrickable 3005pr0018". See keyword_parts().
_KW_PART = re.compile(r"\b(Rebrickable|BrickLink)\s+([A-Za-z0-9][A-Za-z0-9._-]*)",
                      re.IGNORECASE)


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


def keyword_lines(dat: Path) -> list[str]:
    """Every !KEYWORDS line in the .dat's header."""
    if not dat.is_file():
        return []
    out = []
    for line in dat.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("0 "):
            break          # past the header; the geometry starts here
        found = _KW_LINE.match(stripped)
        if found:
            out.append(found.group(1))
    return out


def keyword_parts(dat: Path) -> list[str]:
    """The catalog numbers LDraw's own `!KEYWORDS` line gives this part.

    A print is the case that needs it. LDraw numbers the Gryffindor 1x1 brick
    `3005pz0` and Rebrickable numbers it `3005pr0018`, so nothing about the id
    matches and the part falls through to the plain brick -- which has been
    made since 1954, in 77 colors, and never carried that crest. The .dat says
    which part it is: "Rebrickable 3005pr0018". Rebrickable's own number is
    preferred because the inventories are keyed by it; BrickLink's is a
    fallback for the parts whose numbering the two catalogs share.
    """
    hits: dict[str, str] = {}
    for source, number in _KW_PART.findall(" ; ".join(keyword_lines(dat))):
        hits.setdefault(source.lower(), number)
    return [n for n in (hits.get("rebrickable"), hits.get("bricklink")) if n]


def match(part_id: str, facts: dict[str, tuple[int, int, int, int]],
          designs: dict[str, set[str]],
          named: list[str] = (),
          moulds: frozenset[str] = frozenset()) -> tuple[set[str], str] | None:
    """The Rebrickable numbers to read `part_id`'s years off, and how they
    matched. A set rather than one number: a design id names every mould cut
    from it, and the part's span is the span of all of them.

    `named` is what the .dat's own !KEYWORDS line calls this part, best first,
    and it outranks every route that widens the part -- a print's own numbers
    are the print's, where the base and design routes give it the plain
    mould's.

    `moulds` is every undecorated part the corpus holds, and it is what tells
    a sticker's sheet number from a mould's: both are digits followed by
    letters."""
    if part_id in facts:
        return {part_id}, "exact"
    for number in named:
        if number in facts:
            return {number}, "named"
    printed = _PRINT_SUFFIX.match(part_id)
    if printed and printed.group(1) in facts:
        return {printed.group(1)}, "base"
    sticker = _STICKER.match(part_id)
    if sticker and sticker.group(1) in facts:
        # A number the corpus holds as an undecorated part is the mould this
        # one is a decoration of, not a sheet it ships on -- so the count is
        # the mould's, and `base` is the route that says so.
        return ({sticker.group(1)},
                "base" if sticker.group(1) in moulds else "sheet")
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
    named = keyword_lines(dat)
    if not named:
        return None
    years: list[int] = []
    for ref in _KW_SET.findall(" ; ".join(named)):
        if ref in set_year:
            years.append(set_year[ref])
        else:
            years.extend(bare.get(ref.split("-")[0], ()))
    return (min(years), max(years)) if years else None


def from_prints(plain: dict[str, bool], spans: dict[str, tuple[int, int]],
                obsolete: set[str] = frozenset()) -> list[tuple]:
    """Years for a base mould that was never issued undecorated, read off the
    prints cut from it. `11778` is in no inventory at all -- an eagle wing is
    only ever sold with feathers on it -- while `11778p01` and `11778p02` are
    2013-2014 and 2018-2018, so the mould was in production 2013-2018.

    The envelope, not the overlap: those two prints share no year, and a mould
    that made both existed across the whole span. Its own route, `prints`, so
    nothing mistakes it for a number someone looked up.

    YEARS ONLY. `sets` and `colors` stay 0, and not for want of a figure to
    put there -- inheriting the other direction is a known trap, where
    `3069bp1f` reads 5,766 sets and counts as popular because the plain tile
    it is printed on is. It is no better read this way round.

    `plain` is every part the corpus holds, against whether it is undecorated;
    `spans` is the years already matched. A base with a row of its own is not
    here -- it was issued plain and the inventories know it. `obsolete` is
    read off the base alone: a retired print still dates the mould that cut
    it, so its years count toward a base that is still current.
    """
    prints: dict[str, list[str]] = defaultdict(list)
    for part_id in plain:
        printed = _PRINT_SUFFIX.match(part_id)
        if printed and printed.group(1) in plain:
            prints[printed.group(1)].append(part_id)

    out = []
    for base, kids in prints.items():
        if not plain[base] or base in spans or base in obsolete:
            continue
        known = [spans[k] for k in kids if k in spans]
        if known:
            out.append((base, min(s[0] for s in known),
                        max(s[1] for s in known), 0, "prints", 0))
    return sorted(out)


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
        # `printed` comes with the id: a base mould that inherits from its
        # prints has to be told apart from a print, and the .dat's own
        # description is what says so -- an id suffix is ambiguous.
        part_rows = conn.execute("SELECT id, printed, obsolete FROM parts "
                                 "ORDER BY id").fetchall()
        ids = [r["id"] for r in part_rows]
        plain = {r["id"]: not r["printed"] for r in part_rows}
        moulds = frozenset(i for i, undecorated in plain.items() if undecorated)
        retired = {r["id"] for r in part_rows if r["obsolete"]}
    finally:
        conn.close()
    print(f"{len(ids):,} parts in the corpus", flush=True)

    parts_dir = Path(args.ldraw_dir) / "parts"
    matched = []
    for i, part_id in enumerate(ids, 1):
        if i % 5000 == 0:
            print(f"  matched {i:,}/{len(ids):,}", flush=True)
        hit = match(part_id, facts, designs,
                    keyword_parts(parts_dir / f"{part_id}.dat"), moulds)
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

    # A second pass, because it reads what the first one matched: a base
    # mould nobody ever sold undecorated takes the span of its prints.
    inherited = from_prints(plain, {m[0]: (m[1], m[2]) for m in matched},
                            retired)
    matched.extend(inherited)
    print(f"  {len(inherited):,} base moulds took their years from their prints",
          flush=True)

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
