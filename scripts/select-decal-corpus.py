#!/usr/bin/env python3
"""Choose the extraction-seam corpus: parts that have a surface to print on.

    python scripts/select-decal-corpus.py --out tests/goldens/decal-corpus.txt

A decal binds to a *carrier* — a plane, cylinder or cone the print lies on.
A sculpted part has no such surface: a Marge Simpson head is thousands of tiny
triangles, so every facet becomes its own carrier and the print shatters across
772 of them, none holding more than 3% of it. Those parts cannot exercise the
engine's binding behaviour, only its failure to find a carrier, so they do not
belong in a baseline meant to catch regressions in the former.

The test is the carrier's own size. A print needs somewhere to sit, and the
smallest surface LEGO actually prints on is a 1x1 round tile's face — `98138`
is `4-4disc` scaled by 9, so r=9 LDU. Count the carriers at least that big:

    0            nothing to print on         drop
    1..MAX_BIG   a real printed surface      keep
    > MAX_BIG    shattered, or an assembly   drop

Measured over a stratified sample of the 600-part printed corpus: every clean
part scored exactly 1, the shattered class scored 0 (bar two), and wheel/tyre
assemblies scored 32 and 42.
"""
from __future__ import annotations

import argparse
import math
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import hlr, unwrap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 98138's face: 4-4disc scaled by 9. Note this is r=9, not the 10 the 20 LDU
# stud pitch suggests — the tile's face is inset from its footprint.
# A carrier built from a discretized circle measures slightly UNDER the true
# area of the circle it approximates — a 32-gon at r=9 comes to 252.3 against
# pi*81 = 254.5. Without the margin, a printed 2x2 round tile carrying a r=9
# disc lands 0.85% short and gets dropped. 5% clears every subdivision LDraw
# uses without admitting anything near a facet's size.
TILE_AREA = math.pi * 81.0 * 0.95
MAX_BIG = 4


def carrier_area(carrier, face, regions=()) -> float:
    """Area of the SURFACE, not of the print sitting on it.

    A disc is flat, so the wrap-by-height extent a curved carrier reports is
    zero for one — which scored every 2x2 round tile at 0 and dropped exactly
    the printed-tile class this corpus exists for. Flat carriers get their
    disc/annulus area instead.
    """
    if face is not None:
        # The convex hull, not the polygon. A flat primitive contributes a
        # plane with no facets behind it, so a 2x2 round tile's carrier comes
        # back spanning the full 40 LDU with a self-cancelling area of 61.9 —
        # which dropped the printed-round-tile class outright. The hull is
        # robust to that and errs toward keeping, which is the safer mistake
        # for a corpus.
        return float(face.convex_hull.area)
    if not hasattr(carrier, "R"):
        # A plane that contributed no face polygon: nothing states its extent,
        # so fall back to what is printed on it.
        return float(sum(g.area for _c, g in regions))
    kind = getattr(carrier, "kind", None)
    r = float(np.linalg.norm(carrier.R[:, 0]))
    h = float(np.linalg.norm(carrier.R[:, 1]))
    if kind == "ring":
        inner = float(getattr(carrier, "inner", 0)) * r / max(
            float(getattr(carrier, "inner", 0)) + 1.0, 1e-9)
        return math.pi * max(r * r - inner * inner, 0.0)
    if kind == "disc" or h < 1e-6:
        return math.pi * r * r
    if kind == "con":
        r0 = r * carrier.radius_at(0.0)
        r1 = r * carrier.radius_at(1.0)
        slant = math.hypot(r1 - r0, h)
        return math.pi * (r0 + r1) * slant
    return 2.0 * math.pi * r * h          # cyli


def carrier_areas(part: str, ldraw_dir: str) -> list[float]:
    tris, tri_colors, analytic = hlr.part_geometry(part, ldraw_dir)[:3]
    return [carrier_area(carrier, face, regions)
            for carrier, _t0, regions, face
            in unwrap.decal_groups(tris, tri_colors, analytic)]


def verdict(areas: list[float]) -> tuple[bool, int]:
    big = sum(1 for a in areas if a >= TILE_AREA)
    return (1 <= big <= MAX_BIG), big


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parts", default=str(ROOT / "tests" / "goldens"
                                          / "decal-candidates.txt"))
    ap.add_argument("--out", default=str(ROOT / "tests" / "goldens"
                                        / "decal-corpus.txt"))
    ap.add_argument("--ldraw-dir", default="vendor/ldraw")
    ap.add_argument("--overrides", default=str(ROOT / "tests" / "goldens"
                                               / "corpus-overrides.toml"))
    args = ap.parse_args(argv)

    cand = [ln.split("#")[0].strip()
            for ln in Path(args.parts).read_text().splitlines()]
    cand = [c for c in cand if c]

    ov = {"keep": [], "drop": []}
    if Path(args.overrides).exists():
        ov.update(tomllib.loads(Path(args.overrides).read_text()))
    force_keep, force_drop = set(ov["keep"]), set(ov["drop"])

    kept, dropped, failed = [], [], []
    for i, part in enumerate(cand, 1):
        try:
            areas = carrier_areas(part, args.ldraw_dir)
        except Exception as e:
            failed.append((part, f"{type(e).__name__}: {e}"))
            print(f"{i}/{len(cand)} {part:<14} ERROR {type(e).__name__}",
                  flush=True)
            continue
        ok, big = verdict(areas)
        if part in force_keep:
            ok, why = True, "override"
        elif part in force_drop:
            ok, why = False, "override"
        else:
            why = f"{big} big of {len(areas)}"
        (kept if ok else dropped).append(part)
        print(f"{i}/{len(cand)} {part:<14} {'keep' if ok else 'drop':<4} {why}",
              flush=True)

    header = (
        "# Extraction-seam corpus. Generated by scripts/select-decal-corpus.py;\n"
        "# edit tests/goldens/corpus-overrides.toml, not this file.\n"
        "#\n"
        f"# Kept: a part with 1..{MAX_BIG} carriers of at least "
        f"{TILE_AREA:.1f} LDU^2\n"
        "# (a 1x1 round tile's face). Zero means no surface to print on;\n"
        "# more means the print is shattered across facets, or the part is an\n"
        "# assembly. See the script's docstring for the measurement.\n"
        f"#\n# {len(kept)} kept, {len(dropped)} dropped, {len(failed)} failed "
        f"of {len(cand)} candidates.\n")
    Path(args.out).write_text(header + "\n".join(kept) + "\n")

    print(f"\n{len(kept)} kept, {len(dropped)} dropped, {len(failed)} failed")
    if failed:
        print("failed parts (not in the corpus):")
        for part, err in failed[:10]:
            print(f"  {part}: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
