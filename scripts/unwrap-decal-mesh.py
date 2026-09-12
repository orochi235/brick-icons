#!/usr/bin/env python
"""Flatten a print's own triangles as a texture map, with no carrier at all.

The carrier route asks what exact surface a print sits on, and a sculpted
mould has none. A print is a triangle patch either way, so this welds the
decoration's polygons, takes the largest connected piece and flattens it by
LSCM -- least squares conformal maps, Levy et al. -- which needs only
connectivity and two pinned vertices.

    scripts/unwrap-decal-mesh.py 73152p01 --out out/shards

Reports the distortion it paid: `stretch` is the spread of per-triangle area
scaling, which is what a conformal map trades away to keep angles. A patch
that wraps the whole way round a limb is not a disk and comes back folded
onto itself -- read the stretch before believing the picture.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.sparse import coo_matrix  # noqa: E402
from scipy.sparse.linalg import lsqr  # noqa: E402

from brick_icons import colors as ldcolors  # noqa: E402
from brick_icons.hlr import part_geometry  # noqa: E402

BODY_COLORS = {16, 24, "16", "24"}

#: LDU a vertex may sit from another and still be the same vertex. LDraw
#: parts are unwelded as a matter of course, and a parameterization needs
#: connectivity -- without this every triangle is its own island.
WELD_TOL = 0.01


def decoration(pid, ldraw, weld=WELD_TOL):
    tri, cols, _analytic = part_geometry(pid, ldraw)
    keep = [(np.asarray(t, float).reshape(-1, 3), c)
            for t, c in zip(tri, cols) if c not in BODY_COLORS]
    if not keep:
        return np.zeros((0, 3)), np.zeros((0, 3), int), []
    P = np.vstack([t for t, _c in keep])
    q = np.round(P / weld).astype(np.int64)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    V = np.zeros((len(uniq), 3))
    np.add.at(V, inv, P)
    V /= np.bincount(inv, minlength=len(uniq))[:, None]
    return V, inv.reshape(-1, 3), [c for _t, c in keep]


def largest_component(V, F, cols):
    parent = np.arange(len(V))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in F:
        for a, b in ((f[0], f[1]), (f[1], f[2])):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    root = np.array([find(i) for i in range(len(V))])
    keep_root = np.bincount(root).argmax()
    vmask = root == keep_root
    fmask = vmask[F[:, 0]]
    remap = -np.ones(len(V), int)
    remap[vmask] = np.arange(vmask.sum())
    return (V[vmask], remap[F[fmask]], [c for c, k in zip(cols, fmask) if k],
            float(vmask.sum()) / len(V))


def _local(V, F):
    """Each triangle flattened isometrically into its own plane, and its
    area."""
    p1, p2, p3 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    a, b = p2 - p1, p3 - p1
    la = np.linalg.norm(a, axis=1)
    e1 = a / np.maximum(la, 1e-12)[:, None]
    n = np.cross(a, b)
    area = 0.5 * np.linalg.norm(n, axis=1)
    nh = n / np.maximum(np.linalg.norm(n, axis=1), 1e-12)[:, None]
    e2 = np.cross(nh, e1)
    X = np.column_stack([np.zeros(len(F)), la, (b * e1).sum(1)])
    Y = np.column_stack([np.zeros(len(F)), np.zeros(len(F)), (b * e2).sum(1)])
    return X, Y, area


def lscm(V, F, pins):
    """Conformal uv for every vertex, with `pins` (two indices) held."""
    X, Y, area = _local(V, F)
    ok = area > 1e-12
    F, X, Y, area = F[ok], X[ok], Y[ok], area[ok]
    w = 1.0 / np.sqrt(area)
    # W_j = (x_{j+2} - x_{j+1}) + i (y_{j+2} - y_{j+1}), the conformality
    # residual of Levy's linear system
    Wr = np.column_stack([X[:, 2] - X[:, 1], X[:, 0] - X[:, 2],
                          X[:, 1] - X[:, 0]]) * w[:, None]
    Wi = np.column_stack([Y[:, 2] - Y[:, 1], Y[:, 0] - Y[:, 2],
                          Y[:, 1] - Y[:, 0]]) * w[:, None]

    m = len(V)
    free = np.setdiff1d(np.arange(m), pins)
    col = -np.ones(m, int)
    col[free] = np.arange(len(free))
    nt, nf = len(F), len(free)
    # pinned uv: the two anchors laid on the u axis, which fixes the map's
    # rotation, translation and scale and nothing else
    pin_uv = np.zeros((m, 2))
    pin_uv[pins[1]] = (1.0, 0.0)

    t = np.arange(nt)
    rows, cols_, vals = [], [], []
    rhs = np.zeros(2 * nt)
    for j in range(3):
        v = F[:, j]
        held = col[v] < 0
        for r_off, (cr, ci) in ((0, (Wr[:, j], -Wi[:, j])),
                                (nt, (Wi[:, j], Wr[:, j]))):
            for block, coef in ((0, cr), (nf, ci)):
                free_t = t[~held]
                rows.append(r_off + free_t)
                cols_.append(block + col[v[~held]])
                vals.append(coef[~held])
                if held.any():
                    which = 0 if block == 0 else 1
                    np.add.at(rhs, r_off + t[held],
                              -coef[held] * pin_uv[v[held], which])
    A = coo_matrix((np.concatenate(vals),
                    (np.concatenate(rows), np.concatenate(cols_))),
                   shape=(2 * nt, 2 * nf)).tocsr()
    sol = lsqr(A, rhs, atol=1e-10, btol=1e-10, iter_lim=8000)[0]
    uv = np.zeros((m, 2))
    uv[free, 0] = sol[:nf]
    uv[free, 1] = sol[nf:]
    uv[list(pins)] = pin_uv[list(pins)]
    return uv, F


def stretch(V, F, uv):
    """Spread of per-triangle area scaling -- 1.0 everywhere is isometric."""
    _x, _y, area3 = _local(V, F)
    a, b = uv[F[:, 1]] - uv[F[:, 0]], uv[F[:, 2]] - uv[F[:, 0]]
    area2 = 0.5 * np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0])
    ok = (area3 > 1e-12) & (area2 > 1e-18)
    s = np.sqrt(area2[ok] / area3[ok])
    s = s / np.median(s)
    return float(np.percentile(s, 5)), float(np.percentile(s, 95))


def components(V, F):
    """Size of each connected piece, largest first."""
    parent = np.arange(len(V))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for f in F:
        for a, b in ((f[0], f[1]), (f[1], f[2])):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    root = np.array([find(i) for i in range(len(V))])
    return np.sort(np.bincount(root)[np.bincount(root) > 0])[::-1], root


def draw(V, F, cols, uv, path, px, ldraw):
    lo, hi = uv.min(0), uv.max(0)
    s = px / max(hi[0] - lo[0], hi[1] - lo[1], 1e-12)
    w, h = (hi[0] - lo[0]) * s, (hi[1] - lo[1]) * s
    palette = ldcolors.load_palette(ldraw)
    body = [f'<rect width="{w:.0f}" height="{h:.0f}" fill="white"/>']
    for f, col in zip(F, cols):
        xy = (uv[f] - lo) * s
        pts = " ".join(f"{x:.2f},{h - y:.2f}" for x, y in xy)
        c = palette.by_code.get(int(col)) if str(col).isdigit() else None
        fill = "#%02x%02x%02x" % c.rgb if c else "#888"
        body.append(f'<polygon points="{pts}" fill="{fill}" stroke="{fill}" '
                    f'stroke-width="0.4"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
           f'height="{h:.0f}">' + "".join(body) + "</svg>")
    path.write_text(svg)
    png = path.with_suffix(".png")
    subprocess.run(["resvg", str(path), str(png)], check=True)
    return png


def flatten(pid, ldraw, weld):
    """(tris, welded verts, pieces, largest share, p5, p95, V, F, cols, uv)."""
    V, F, cols = decoration(pid, ldraw, weld)
    if not len(F):
        return None
    sizes, _root = components(V, F)
    V, F, cols, share = largest_component(V, F, cols)
    if len(F) < 2:
        return None
    d = np.linalg.norm(V - V.mean(0), axis=1)
    p0 = int(d.argmax())
    p1 = int(np.linalg.norm(V - V[p0], axis=1).argmax())
    uv, F2 = lscm(V, F, (p0, p1))
    keep = [c for c, _f in zip(cols, F)][:len(F2)] if len(F2) != len(F) else cols
    lo, hi = stretch(V, F2, uv)
    return dict(tris=len(F), verts=len(V) / max(share, 1e-9), pieces=len(sizes),
                share=share, p5=lo, p95=hi, V=V, F=F2, cols=keep, uv=uv)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--from-csv", help="a CSV with a part_id column; its "
                    "parts are the set")
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--weld", type=float, default=WELD_TOL)
    ap.add_argument("--px", type=int, default=900)
    ap.add_argument("--draw", action="store_true",
                    help="also write an SVG and PNG per part")
    ap.add_argument("--csv", help="write a row per part here")
    ap.add_argument("--out", default="out/shards")
    args = ap.parse_args(argv)

    picks = list(args.parts)
    if args.from_csv:
        import csv as _csv
        picks += [r["part_id"] for r in _csv.DictReader(open(args.from_csv))]
    if not picks:
        ap.error("name some parts, or pass --from-csv")
    draw_it = args.draw or (not args.csv and len(picks) <= 8)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fh = open(args.csv, "w", newline="") if args.csv else None
    w = None
    if fh:
        import csv as _csv
        w = _csv.writer(fh)
        w.writerow(["part_id", "tris", "pieces", "largest_share",
                    "area_p5", "area_p95", "secs"])
    whole = 0
    for i, pid in enumerate(picks, 1):
        t0 = time.time()
        try:
            r = flatten(pid, args.ldraw, args.weld)
        except Exception as exc:
            r = None
            note = f"error: {type(exc).__name__}: {exc}"
        else:
            note = "no decoration" if r is None else ""
        secs = time.time() - t0
        if r is None:
            print(f"{i}/{len(picks)}  {pid:16s} {note} ({secs:.1f}s)", flush=True)
            if w:
                w.writerow([pid, 0, 0, 0, "", "", f"{secs:.2f}"])
                fh.flush()
            continue
        if r["share"] >= 0.99:
            whole += 1
        print(f"{i}/{len(picks)}  {pid:16s} {r['tris']:5d} tris  "
              f"{r['pieces']:3d} pieces, largest {r['share']:5.0%}  "
              f"area {r['p5']:.2f}..{r['p95']:.2f}  ({secs:.1f}s)", flush=True)
        if w:
            w.writerow([pid, r["tris"], r["pieces"], f"{r['share']:.4f}",
                        f"{r['p5']:.3f}", f"{r['p95']:.3f}", f"{secs:.2f}"])
            fh.flush()
        if draw_it:
            png = draw(r["V"], r["F"], r["cols"], r["uv"],
                       out / f"{pid}.lscm.svg", args.px, args.ldraw)
            print(f"      -> {png}", flush=True)
    if fh:
        fh.close()
        print(f"\n{len(picks)} parts -> {args.csv}")
        print(f"  {whole} weld into a single connected piece")
    return 0


if __name__ == "__main__":
    sys.exit(main())
