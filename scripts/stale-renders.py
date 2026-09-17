#!/usr/bin/env python3
"""Drawn renders whose build predates the drawing code, per slot.

    .venv/bin/python scripts/stale-renders.py
    .venv/bin/python scripts/stale-renders.py --slot occt --out out/slot-occt-refresh/parts.txt

`slot-coverage.py --only stale` answers a different question: it is the
ERRORED parts that have not met the current revision, which is a retry class.
This one is the drawn ones -- a render that succeeded and is now a picture of
an older engine. Nothing in the gap counts here, and a slot can be 100% drawn
and 100% stale at the same time.

A render is stale when some commit touching the drawing path is reachable from
HEAD and not from the build that drew it. `DRAWING` is that path; a module
outside it (db, tags, stats, the lab) cannot move a pixel, so a commit to one
must not cost the fleet a redraw.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

#: The modules a drawing passes through. Everything reachable from
#: `cli.process_one` down to the SVG, and nothing that only reads the result.
DRAWING = [
    "brick_icons/arcfit.py", "brick_icons/cli.py", "brick_icons/colors.py",
    "brick_icons/config.py", "brick_icons/cqsvg.py", "brick_icons/geom2d.py",
    "brick_icons/hlr.py", "brick_icons/library.py", "brick_icons/occt.py",
    "brick_icons/primitives.py", "brick_icons/process.py",
    "brick_icons/render.py", "brick_icons/repair.py", "brick_icons/shade.py",
    "brick_icons/trace.py", "brick_icons/unwrap.py",
]


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                          capture_output=True, text=True).stdout.strip()


def behind(commit: str | None, head: str) -> list[str]:
    """Drawing commits `commit` is missing. An unknown or absent build is
    maximally stale -- it cannot prove it has anything."""
    if not commit or not _git("cat-file", "-t", commit) == "commit":
        return ["(build unknown)"]
    out = _git("log", "--oneline", f"{commit}..{head}", "--", *DRAWING)
    return out.splitlines()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(ROOT / db.DEFAULT_PATH))
    ap.add_argument("--slot", help="write this slot's stale part ids")
    ap.add_argument("--out", type=Path, help="write the part ids here")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--min-behind", type=int, default=1,
                    help="only parts missing at least this many drawing commits")
    a = ap.parse_args(argv)

    head = _git("rev-parse", "--short", a.head)
    conn = db.connect(a.db)
    rows = conn.execute("""select r.source, u.commit_sha, count(*) n
                             from renders r left join runs u on u.id = r.run_id
                            group by 1, 2""").fetchall()

    cache: dict[str | None, list[str]] = {}
    per_slot: dict[str, list[tuple[str | None, int, int]]] = {}
    for source, sha, n in rows:
        if sha not in cache:
            cache[sha] = behind(sha, head)
        per_slot.setdefault(source, []).append((sha, n, len(cache[sha])))

    print(f"drawing code at {head}; a render is stale when its build misses "
          f"any of {len(DRAWING)} modules' commits\n")
    print(f"  {'slot':20s} {'drawn':>7s} {'stale':>7s} {'fresh':>7s}  worst gap")
    for source in sorted(per_slot, key=lambda s: -sum(
            n for _, n, b in per_slot[s] if b)):
        drawn = sum(n for _, n, _ in per_slot[source])
        stale = sum(n for _, n, b in per_slot[source] if b)
        worst = max(b for _, _, b in per_slot[source])
        print(f"  {source:20s} {drawn:7d} {stale:7d} {drawn - stale:7d}  "
              f"{worst:3d} commits")

    if a.slot:
        gap = {sha: len(miss) for sha, miss in cache.items()}
        ids = [r[0] for r in conn.execute(
            """select r.part_id, u.commit_sha from renders r
                 left join runs u on u.id = r.run_id
                where r.source = ? order by r.part_id""", (a.slot,))
            if gap.get(r[1], 0) >= a.min_behind]
        print(f"\n{a.slot}: {len(ids)} parts at least {a.min_behind} "
              f"drawing commits behind")
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text("\n".join(ids) + "\n")
            print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
