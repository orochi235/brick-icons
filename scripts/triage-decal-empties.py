#!/usr/bin/env python
"""Why a slot ran on a part and drew nothing.

`state='none'` with no error means the renderer finished and produced no
drawing. On a printed part that is the decoration finder giving up, and the
question is always the same: was there anything to find? This sorts the
parts by what their `.dat` actually holds, so the finder's gap can be sized
before anyone opens `unwrap.py`.

    scripts/triage-decal-empties.py --out out/decal-triage.csv

Colors 16 and 24 are "whatever color the caller asked for" and the edge
color, so a polygon in either is body, not decoration. Anything else is a
fixed color the author chose, which on a printed part is what the print is
made of.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

#: How deep a subfile chain is followed. `features.MAX_DEPTH` uses the same.
MAX_DEPTH = 30

BODY_COLORS = {"16", "24"}


def roots(ldraw: Path) -> list[Path]:
    return [ldraw / "parts", ldraw / "p", ldraw / "parts" / "s",
            ldraw / "p" / "48"]


def resolve(name: str, where: list[Path]) -> Path | None:
    name = name.replace("\\", "/").strip()
    for root in where:
        p = root / name
        if p.exists():
            return p
    stem = name.rsplit("/", 1)[-1]
    for root in where:
        p = root / stem
        if p.exists():
            return p
    return None


def scan(path: Path, where: list[Path], limit: int = MAX_DEPTH,
         depth: int = 0,
         seen: set[Path] | None = None) -> tuple[set[str], bool, int]:
    """Decoration colors found, whether a TEXMAP is declared, and how many
    subfile references were followed. `limit=0` reads the part file alone."""
    seen = seen if seen is not None else set()
    if depth > limit or path in seen:
        return set(), False, 0
    seen.add(path)
    colors: set[str] = set()
    texmap = False
    subs = 0
    try:
        lines = path.open(encoding="latin-1").read().splitlines()
    except OSError:
        return colors, texmap, subs
    for line in lines:
        f = line.split()
        if not f:
            continue
        if f[0] == "0":
            if len(f) > 1 and f[1].upper().startswith("!TEXMAP"):
                texmap = True
            continue
        if f[0] in ("3", "4") and len(f) > 1 and f[1] not in BODY_COLORS:
            colors.add(f[1])
        elif f[0] == "1" and len(f) >= 15:
            subs += 1
            child = resolve(f[14], where)
            if child is not None:
                c, t, s = scan(child, where, limit=limit, depth=depth + 1,
                               seen=seen)
                colors |= c
                texmap = texmap or t
                subs += s
    return colors, texmap, subs


def classify(top: set[str], deep: set[str], texmap: bool,
             found: bool) -> str:
    if not found:
        return "no part file"
    if top:
        return "color in the part itself"
    if deep:
        return "color only in a subfile"
    if texmap:
        return "texmap image, no colored polys"
    return "no decoration in the geometry"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="corpus.db")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--source", default="decal")
    ap.add_argument("--out", default="out/decal-triage.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT p.id, p.title FROM parts p "
        "WHERE p.printed = 1 AND p.obsolete = 0 "
        "  AND EXISTS (SELECT 1 FROM attempts a WHERE a.part_id = p.id "
        "              AND a.source = ? AND a.state = 'none') "
        "  AND NOT EXISTS (SELECT 1 FROM renders r WHERE r.part_id = p.id "
        "                  AND r.source = ?) "
        "ORDER BY p.id", (args.source, args.source)))
    if args.limit:
        rows = rows[:args.limit]

    ldraw = Path(args.ldraw)
    where = roots(ldraw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tally: dict[str, int] = {}

    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "class", "top_colors", "deep_colors",
                    "texmap", "subfiles", "title"])
        for i, row in enumerate(rows, 1):
            pid = row["id"]
            path = resolve(f"{pid}.dat", where)
            if path is None:
                top, deep, texmap, subs = set(), set(), False, 0
                found = False
            else:
                found = True
                top, texmap_top, _ = scan(path, where, limit=0)
                deep, texmap, subs = scan(path, where)
                texmap = texmap or texmap_top
                deep = deep - top
            kind = classify(top, deep, texmap, found)
            tally[kind] = tally.get(kind, 0) + 1
            w.writerow([pid, kind, " ".join(sorted(top)),
                        " ".join(sorted(deep)), int(texmap), subs,
                        row["title"]])
            print(f"{i}/{len(rows)}  {pid:16s} {kind}", flush=True)

    print(f"\n{len(rows)} parts -> {out}")
    for kind, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n:6d}  {kind}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
