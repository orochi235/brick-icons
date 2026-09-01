"""Which authored edges does one engine draw that the other does not?

Answers "occt dropped an edge" without guessing which edge. Every authored
type-2 segment is asked of BOTH engines by its own 3D identity, so the two
answers are about the same edge -- naive's `VisResult` carries its own
`Projection`, which is what makes the comparison possible.

Two measures that look equivalent and are not, both tried and discarded:
counting authored loci with no surviving occt fragment cannot tell a
legitimately hidden edge from a dropped one (it reports 20+ on a part missing
one edge), and selecting an edge by its projected 2D length matches a
DIFFERENT edge at each angle, which manufactures a convincing false "the
visibility flickers with the angle" result. Key on 3D endpoints.

**Only trust this on a part with no arcfit-claimed chains.** `naive_draws`
matches against LINE ops, so a segment naive drew as part of a fitted ARC
reads as not-drawn and lands in `naive-only`'s complement -- inflating
`occt-only` into the dozens. 4070 and 3673 have no fitted chains and report
1 and 5; 4019 and 6589 do, and report 87 and 54 of pure noise. The tell is a
disagreement count of the same order as `both`.

`neither` is not "correct": an edge BOTH engines wrongly drop sits there,
invisible to this tool. It finds disagreements, not defects.

    scripts/compare-engine-visibility.py 4070 --angle 30,45
"""
from __future__ import annotations

import argparse
import numpy as np

from brick_icons import hlr, occt


def _cross2(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def naive_draws(seg, res, tol_px=1.5, cover=0.6):
    """Is `seg` covered by naive's drawn line ops? Sampled along the segment
    rather than endpoint-matched: HLR splits an edge into visible pieces, so a
    partly-occluded edge is several ops and matches no single one."""
    px, py, _ = res.proj.to_px(seg)
    a, b = np.array([px[0], py[0]]), np.array([px[1], py[1]])
    d = b - a
    n = float(np.linalg.norm(d))
    if n < 1e-9:
        return False
    ts = np.linspace(0.0, 1.0, 21)
    hit = np.zeros(ts.size, bool)
    for op in res.segs:
        if op[0] != "line":
            continue
        p, q = np.array([op[1], op[2]]), np.array([op[3], op[4]])
        e = q - p
        m = float(np.linalg.norm(e))
        if m < 1e-9 or abs(_cross2(d / n, e / m)) > 0.02:
            continue
        for i, t in enumerate(ts):
            w = a + t * d - p
            u = float(w @ e) / (m * m)
            if -0.02 < u < 1.02 and abs(_cross2(e / m, w)) < tol_px:
                hit[i] = True
    return bool(hit.mean() > cover)


def occt_visible_pts(shape, right, up):
    pts = []
    comps = occt.hlr_edges(shape, right, up, cull=True)
    for name in ("sharp", "outline"):
        comp = comps.get(name)
        if comp is None:
            continue
        for edge in occt._edges_of(comp):
            try:
                pts.append(occt._fragment_points(edge))
            except Exception:                      # noqa: BLE001
                continue
    return pts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part")
    ap.add_argument("--angle", default="30,45")
    ap.add_argument("--root", default="vendor/ldraw")
    ap.add_argument("--render-px", type=int, default=512)
    args = ap.parse_args(argv)

    lat, long = (float(v) for v in args.angle.split(","))
    right, up, fwd = hlr.view_basis(lat, long)
    res = hlr.visible_segments(args.part, args.root, lat=lat, long=long,
                               render_px=args.render_px, engine="naive")
    out = occt.flatten_part(args.part, args.root)
    shape = occt.build_shape(out)
    vis = occt_visible_pts(shape, right, up)
    ax, ay = occt._screen_axes(right, up)

    both = neither = 0
    only_naive, only_occt = [], []
    segs = [np.asarray(s, float) for s in out["2"]]
    for seg in segs:
        n_ = naive_draws(seg, res)
        locus = occt._seg_locus(seg[0], seg[1], "line", ax, ay)
        o_ = any(occt._on_locus(q, locus) for q in vis)
        if n_ and o_:
            both += 1
        elif n_:
            only_naive.append(seg)
        elif o_:
            only_occt.append(seg)
        else:
            neither += 1

    print(f"{args.part} at {args.angle}: {len(segs)} authored segments")
    print(f"  both={both}  naive-only={len(only_naive)}  "
          f"occt-only={len(only_occt)}  neither={neither}")
    for tag, group in (("NAIVE ONLY", only_naive), ("OCCT ONLY", only_occt)):
        for seg in group:
            print(f"  {tag}  {np.round(seg[0], 2)} -> {np.round(seg[1], 2)}"
                  f"  len={float(np.linalg.norm(seg[1] - seg[0])):6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
