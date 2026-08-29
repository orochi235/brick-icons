"""How far a printed part's decal sits from the wall it decorates.

Phase 2 of docs/superpowers/specs/2026-08-28-printed-parts-design.md binds a
decal facet to a carrier surface when it lies within some tolerance of it. That
tolerance is the design's one free parameter, and picking it by eye risks
either never binding or swallowing standoff geometry that is meant to stand
proud. This reports the real numbers.

For every '1 <code> ...' subfile reference in a part it records, per color code:
  * centred primitives (on the part axis) -> the surface radius is the
    reference matrix's horizontal scale
  * off-axis primitives (a decal patch laid on the wall) -> the radius is the
    distance from the axis to where it was placed

Color 16 means "inherit the part color" and marks body geometry; any other code
is decoration. The gap between the two sets is what phase 2 must close.

Usage: .venv/bin/python scripts/measure-decal-offsets.py [part-id ...]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

PARTS = Path("vendor/ldraw/parts")
CURVED = ("cyli", "con", "ndis", "disc", "chrd", "ring")
DEFAULT_IDS = ["3941p01", "3062bp01", "3942bp01", "4740p01", "3960p01",
               "6141p01", "3068bp00", "3001p01", "3626bp01", "3040bp08"]


IDENTITY = (1, 0, 0, 0, 1, 0, 0, 0, 1)


def _subpart(t: list) -> Path | None:
    """An s/ subpart referenced with an identity transform, or None.

    Only s/ files, because p/ holds UNIT primitives whose real radius lives in
    the caller's matrix, not in their own vertices — recursing into those
    reports every wall as radius 1. Only identity transforms, because this
    script does not carry a matrix down and a rotated subpart's radii would be
    silently wrong. Anything else is measured at this level or not at all.
    """
    ref = t[14].replace("\\", "/")
    if not ref.lower().startswith("s/"):
        return None
    m = tuple(float(v) for v in t[5:14])
    trans = tuple(float(v) for v in t[2:5])
    if any(abs(a - b) > 1e-9 for a, b in zip(m, IDENTITY)) or any(trans):
        return None
    cand = PARTS / "s" / ref.split("/")[-1]
    return cand if cand.exists() else None


def surfaces(path: Path, depth: int = 0):
    """(color, radius, what) for curved refs AND for raw polygons.

    Decoration is not only subfile references: 3941p01 builds its black panel
    field from 36 type-4 quads, so a refs-only scan reports it as having no
    decal at all. Several parts also stash the print in an s/ subpart, hence
    the recursion — without it 3942bp01 and 3068bp00 look undecorated.
    """
    for ln in path.read_text(errors="replace").splitlines():
        t = ln.split()
        if not t:
            continue
        if t[0] == "1" and len(t) >= 15 and depth < 3:
            sub = _subpart(t)
            if sub is not None:
                # an inherit-colored subpart carries the parent's code down;
                # one referenced in an explicit color paints all of its content
                parent = int(t[1])
                for code, r, what in surfaces(sub, depth + 1):
                    yield (code if parent == 16 else parent), r, what
        if t[0] == "1" and len(t) >= 15:
            prim = t[14].replace("\\", "/").split("/")[-1].lower()
            if not any(k in prim for k in CURVED):
                continue
            x, _y, z = (float(v) for v in t[2:5])
            a, _b, c, _d, _e, _f, g, _h, i = (float(v) for v in t[5:14])
            off = math.hypot(x, z)
            # a primitive on the axis carries its radius in the matrix; one
            # placed out on the wall carries it in the translation
            scale = math.hypot(a, g) or math.hypot(c, i)
            yield int(t[1]), (scale if off < 1e-6 else off), prim
        elif t[0] in ("3", "4"):
            n = 3 if t[0] == "3" else 4
            if len(t) < 2 + 3 * n:
                continue
            v = [float(x) for x in t[2:2 + 3 * n]]
            pts = [v[k:k + 3] for k in range(0, 3 * n, 3)]
            r = sum(math.hypot(p[0], p[2]) for p in pts) / n
            yield int(t[1]), r, f"poly{n}"


def report(pid: str) -> None:
    f = PARTS / f"{pid}.dat"
    if not f.exists():
        print(f"{pid:<10} MISSING")
        return
    body, decal = {}, {}
    for code, r, prim in surfaces(f):
        (body if code == 16 else decal).setdefault(round(r, 3), set()).add(prim)
    if not decal:
        print(f"{pid:<10} no decal geometry (color-16 only)")
        return
    if not body:
        print(f"{pid:<10} decal radii {sorted(decal)[:6]} | no body carrier found")
        return
    gaps = [(d, min(body, key=lambda b: abs(b - d))) for d in sorted(decal)]
    worst = max(abs(d - b) for d, b in gaps)
    best = min(abs(d - b) for d, b in gaps)
    print(f"{pid:<10} body {sorted(body)[:4]}")
    print(f"{'':<10} decal {sorted(decal)[:6]}")
    print(f"{'':<10} decal-to-carrier gap: min {best:.3f}  max {worst:.3f} LDU")


def main(argv) -> int:
    ids = argv[1:] or DEFAULT_IDS
    for i, pid in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}]", end=" ")
        report(pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
