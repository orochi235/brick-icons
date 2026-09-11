#!/usr/bin/env python3
"""Which decal drawings the carrier-axis rule changed, and so want redrawing.

    .venv/bin/python scripts/decal-axis-affected.py --out affected.txt
    .venv/bin/python scripts/decal-axis-affected.py --list batch.txt --out a.txt

`unwrap.axis_reversed` turns a curved carrier whose authored axis runs against
LDraw up, so every decal already in the store that bound to one is drawn
upside down. A part is affected when the carrier its decoration actually
BINDS to is reversed -- having a reversed cylinder somewhere is not enough,
and over a 250-part sample that looser test flagged 95 where 16 were real.

Two passes, because the loose test is 24x cheaper and never misses: reading a
part's geometry is ~0.01s, binding its decoration to a carrier ~0.23s. The
first pass drops the parts that cannot be affected, the second asks the real
question of what is left.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import hlr, unwrap  # noqa: E402


def has_reversed_primitive(analytic) -> bool:
    """The cheap test: any curved primitive at all with a reversed axis.

    A superset of the answer -- a decal's carrier is one of these primitives
    (or, for a tall cone, a family of them), so a part whose carrier is
    reversed always has one. Validated against the binding test over 250
    parts: 16 affected, 16 caught, 0 missed.
    """
    return any(getattr(p, "kind", None) in ("cyli", "con")
               and unwrap.axis_reversed(p) for p in analytic)


def binds_to_reversed(tris, tri_colors, analytic) -> bool:
    """The real test: the carrier this part's decoration binds to is reversed."""
    for carrier, _theta0, _regions, _face in unwrap.significant_groups(
            unwrap.decal_groups(tris, tri_colors, analytic)):
        if carrier is None or isinstance(carrier, unwrap.Plane):
            continue
        if unwrap.axis_reversed(carrier):
            return True
    return False


def parts_with_a_decal(db: str) -> list[str]:
    conn = sqlite3.connect(db)
    return sorted(r[0] for r in conn.execute(
        "SELECT part_id FROM renders WHERE source = 'decal'"))


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--list", help="part ids, one per line (default: every "
                                  "part with a decal in the store)")
    p.add_argument("--db", default="corpus.db")
    p.add_argument("--ldraw-dir", default="vendor/ldraw")
    p.add_argument("--out", required=True, help="write the affected ids here")
    args = p.parse_args(argv)

    if args.list:
        parts = [x.strip() for x in Path(args.list).read_text().split() if x.strip()]
    else:
        parts = parts_with_a_decal(args.db)

    hits, unreadable, t0 = [], 0, time.time()
    for i, part in enumerate(parts, 1):
        try:
            tris, colors, analytic = hlr.part_geometry(part, args.ldraw_dir)
            # A part whose geometry will not load cannot be cleared, so it is
            # kept: redrawing one that did not need it costs a render, and
            # dropping one that did leaves it upside down for good.
            affected = (has_reversed_primitive(analytic)
                        and binds_to_reversed(tris, colors, analytic))
        except Exception as exc:
            unreadable += 1
            affected = True
            print(f"{i}/{len(parts)} {part}: {type(exc).__name__}, kept", flush=True)
        else:
            print(f"{i}/{len(parts)} {part}: "
                  f"{'AFFECTED' if affected else 'clean'}", flush=True)
        if affected:
            hits.append(part)

    Path(args.out).write_text("\n".join(hits) + "\n" if hits else "")
    print(f"\n{len(hits)} of {len(parts)} affected "
          f"({unreadable} kept unread) in {time.time() - t0:.0f}s -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
