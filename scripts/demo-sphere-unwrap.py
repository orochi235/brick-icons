#!/usr/bin/env python
"""Feasibility demo: reassemble a shattered dome print on a fitted sphere.

NOT part of the renderer, and nothing imports it. `decal_groups` binds a
dome print to one plane per facet, so a Batman logo on a Dish 4 x 4 comes
back as 36 shards and draws nothing. Its vertices all lie on one sphere, so
this fits that sphere and lays every shard down in ONE azimuthal-equidistant
map about the sphere's axis -- distance from the pole to scale, azimuth
around it, which is what flattening a logo printed on a dome means.

    scripts/demo-sphere-unwrap.py 3960pb0 --out out/shards

Answers "could the fragments be reassembled" with a picture. It says nothing
about the two harder cases: a print over several genuinely distinct flat
faces, and one on a freeform sculpt that fits no surface at all.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from brick_icons import colors as ldcolors  # noqa: E402
from brick_icons.hlr import part_geometry  # noqa: E402

BODY_COLORS = {16, 24, "16", "24"}


def fit_sphere(P):
    A = np.hstack([2 * P, np.ones((len(P), 1))])
    x, *_ = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)
    c = x[:3]
    return c, float(np.sqrt(x[3] + c @ c))


def azimuthal(P, c, r, axis=(0., 1., 0.)):
    """Distance from the pole along the surface, carried around by azimuth."""
    a = np.asarray(axis, float)
    d = P - c
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    # measure from whichever pole the print is nearer. An inverted dish sits
    # on the far side of its own fitted sphere, and arc length from the near
    # pole then runs to almost half a circumference -- a band 300 LDU out and
    # 25 wide, which draws the print as a hairline ring.
    if float(np.mean(d @ a)) < 0:
        a = -a
    e1 = np.array([a[1], a[2], a[0]], float)
    e1 = e1 - a * (e1 @ a)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    rho = r * np.arccos(np.clip(d @ a, -1.0, 1.0))
    th = np.arctan2(d @ e2, d @ e1)
    return np.column_stack([rho * np.cos(th), rho * np.sin(th)])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("part")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--axis", default="y", choices=("x", "y", "z"))
    ap.add_argument("--out", default="out/shards")
    args = ap.parse_args(argv)

    tri, cols, _analytic = part_geometry(args.part, args.ldraw)
    deco = [(np.asarray(t, float).reshape(-1, 3), c)
            for t, c in zip(tri, cols) if c not in BODY_COLORS]
    if not deco:
        print(f"{args.part}: no decoration")
        return 1
    P = np.vstack([t for t, _c in deco])
    c, r = fit_sphere(P)
    resid = np.abs(np.linalg.norm(P - c, axis=1) - r)
    print(f"{args.part}: {len(deco)} decoration facets on a sphere "
          f"r={r:.1f}, p95 residual {np.percentile(resid, 95):.3f} LDU")

    axis = {"x": (1., 0., 0.), "y": (0., 1., 0.), "z": (0., 0., 1.)}[args.axis]
    uv = [(azimuthal(t, c, r, axis), col) for t, col in deco]
    flat = np.vstack([q for q, _c in uv])
    lo, hi = flat.min(0), flat.max(0)
    s = args.px / max(hi[0] - lo[0], hi[1] - lo[1], 1e-9)
    w, h = (hi[0] - lo[0]) * s, (hi[1] - lo[1]) * s

    palette = ldcolors.load_palette(args.ldraw)
    body = [f'<rect width="{w:.0f}" height="{h:.0f}" fill="white"/>']
    for q, col in uv:
        xy = (q - lo) * s
        pts = " ".join(f"{x:.2f},{h - y:.2f}" for x, y in xy)
        rgb = palette.by_code.get(int(col)) if str(col).isdigit() else None
        fill = "#%02x%02x%02x" % rgb.rgb if rgb else "#888"
        body.append(f'<polygon points="{pts}" fill="{fill}" '
                    f'stroke="{fill}" stroke-width="0.6"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
           f'height="{h:.0f}">' + "".join(body) + "</svg>")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.part}.sphere.svg"
    path.write_text(svg)
    png = path.with_suffix(".png")
    subprocess.run(["resvg", str(path), str(png)], check=True)
    print(f"  -> {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
