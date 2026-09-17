#!/usr/bin/env python3
"""Draw parts at HEAD and score them against the edges they declare.

    .venv/bin/python scripts/edge-gaps-now.py --source occt 3437 34816 38583
    .venv/bin/python scripts/edge-gaps-now.py --open-defects --source occt \
        --overlay out/edge-overlays

`score-declared-edges.py` scores STORED drawings -- the corpus SVGs and the
`.fit.json` beside them. This draws first, so it answers the triage question
that one cannot: does the engine still leave out a declared edge TODAY, on a
part somebody filed a "missing contours" defect against weeks ago.

**A zero here refutes "missing lines"; it refutes nothing else.** The oracle
scores what the .dat declares as type-2 edges against what the drawing inks,
so it is silent on extra ink, on shading, on a surface that is missing without
an edge to mark it, and on a part that declares no edges at all -- which
scores 0 of 0 px and means only that the question was not asked. Read the
declared total, not just the gap count.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

DEFECTS = ROOT / "tests" / "goldens" / "defects.toml"
#: Titles a missing-linework oracle has anything to say about.
LINEWORK = re.compile(r"missing|outline|contour|\bline\b|\barc\b|edge")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--source", default="occt")
    ap.add_argument("--open-defects", action="store_true",
                    help="every open defect whose title names linework")
    ap.add_argument("--overlay", type=Path)
    ap.add_argument("--tmp", type=Path, default=Path("/tmp/edge-gaps-now"))
    a = ap.parse_args(argv)

    parts = list(a.parts)
    if a.open_defects:
        for r in tomllib.load(DEFECTS.open("rb"))["defect"]:
            if (r.get("status") == "open"
                    and a.source.split("-")[-1] in r.get("engines", [])
                    and LINEWORK.search(r["title"].lower())
                    and r["part"] not in parts):
                parts.append(r["part"])
    if not parts:
        ap.error("no parts")

    argv_slot = list(db._CANONICAL[a.source])
    if "--format" not in argv_slot:
        argv_slot += ["--format", "svg"]
    svgs = []
    for i, p in enumerate(parts, 1):
        into = a.tmp / a.source / p
        into.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m",
                            "brick_icons.cli", p, *argv_slot,
                            "--out", str(into)],
                           capture_output=True, text=True, cwd=ROOT)
        found = sorted(into.glob(f"{p}.*svg"))
        print(f"draw {i:3d}/{len(parts)} {p:14s} "
              f"{'ok' if found else 'FAILED'}", flush=True)
        svgs.extend(str(s) for s in found)

    if not svgs:
        print("nothing drew", file=sys.stderr)
        return 1
    listing = a.tmp / f"{a.source}-list.txt"
    listing.write_text("\n".join(svgs) + "\n")
    cmd = [str(ROOT / ".venv/bin/python"),
           str(ROOT / "scripts" / "score-declared-edges.py"),
           "--source", a.source, "--list", str(listing)]
    if a.overlay:
        cmd += ["--overlay", str(a.overlay)]
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
