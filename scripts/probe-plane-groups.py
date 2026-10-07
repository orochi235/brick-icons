"""Which planar faces occt._group_planes unions, for faces inside a world box.

Wraps the grouping step of a real CLI render and prints, for every planar face
whose outer wire lies inside --box, its world normal, its vertices and the
group it was put in. Two facets of one smooth surface in different groups is
a tone step in the fill; this names the facets and the edge between them.

    .venv/bin/python scripts/probe-plane-groups.py 32062 --box 17,-7,-7,21,7,7 \\
        -- --shading outline --shade-style flat3
    .venv/bin/python scripts/probe-plane-groups.py 3649 --changed -- ...
"""
import argparse
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from brick_icons import cli, occt  # noqa: E402


def main():
    argv = sys.argv[1:]
    extra = []
    if "--" in argv:
        k = argv.index("--")
        argv, extra = argv[:k], argv[k + 1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--box", default="-1e9,-1e9,-1e9,1e9,1e9,1e9",
                    help="x0,y0,z0,x1,y1,z1 world LDU")
    ap.add_argument("--changed", action="store_true",
                    help="print only the groups quad-diagonal seams join")
    a = ap.parse_args(argv)
    b = np.array([float(v) for v in a.box.split(",")]).reshape(2, 3)
    orig = occt._group_planes

    def changed(shape, out, plane_by_idx):
        """Print every group the quad-diagonal seams join, then leave the
        faces grouped as this tree would."""
        parts = {}
        for flag in (False, True):
            occt.QUAD_DIAGONAL_SEAMS = flag
            orig(shape, out, plane_by_idx)
            parts[flag] = {idx: f["group"] for idx, f in plane_by_idx.items()}
        occt.QUAD_DIAGONAL_SEAMS = True
        joined = defaultdict(set)
        for idx, g in parts[True].items():
            joined[g].add(parts[False][idx])
        for g, olds in joined.items():
            if len(olds) < 2:
                continue
            print(f"joined {len(olds)} groups:")
            for old in sorted(olds):
                for idx, f in sorted(plane_by_idx.items()):
                    if parts[False][idx] != old:
                        continue
                    W, n = f["_plane3"]
                    uniq = np.unique(np.round(np.asarray(W, float), 3), axis=0)
                    vs = " ".join("(" + ",".join(f"{c:.3f}" for c in v) + ")"
                                  for v in uniq[:8])
                    print(f"  old {old % 9973:4d} face {idx:4d} "
                          f"n ({n[0]:+.3f},{n[1]:+.3f},{n[2]:+.3f}) {vs}")
        sys.stdout.flush()

    from brick_icons import shade
    mask0 = shade._seam_edge_mask

    def edges_by_diagonal(A, B, declared, **kw):
        """Under --changed: print each sewn edge only a quad diagonal seams,
        with the diagonal it lies on."""
        m = mask0(A, B, declared, **kw)
        if occt.QUAD_DIAGONAL_SEAMS:
            cond = mask0(A, B, list(out_ref[0].get("5") or []))
            fmt = lambda p: "(" + ",".join(f"{c:.3f}" for c in p) + ")"
            for i in np.flatnonzero(m & ~cond):
                hit = [d for d in occt._quad_diagonals(out_ref[0])
                       if mask0(A[i:i + 1], B[i:i + 1], [d])[0]]
                print(f"  diag-seam edge {fmt(A[i])}-{fmt(B[i])}  on "
                      + " ".join(f"{fmt(d[0])}-{fmt(d[1])}" for d in hit[:3]))
        return m

    out_ref = [None]

    def probe(shape, out, plane_by_idx):
        out_ref[0] = out
        if a.changed:
            shade._seam_edge_mask = edges_by_diagonal
            try:
                return changed(shape, out, plane_by_idx)
            finally:
                shade._seam_edge_mask = mask0
        if a.changed:
            return changed(shape, out, plane_by_idx)
        orig(shape, out, plane_by_idx)
        names = {}
        rows = []
        for idx, f in sorted(plane_by_idx.items()):
            W, n = f["_plane3"]
            W = np.asarray(W, float)
            if not ((W >= b[0] - 1e-6).all() and (W <= b[1] + 1e-6).all()):
                continue
            g = names.setdefault(f["group"], len(names))
            rows.append((g, idx, n, W))
        for g, idx, n, W in sorted(rows, key=lambda r: (r[0], r[1])):
            uniq = np.unique(np.round(W, 3), axis=0)
            vs = " ".join("(" + ",".join(f"{c:.3f}" for c in v) + ")" for v in uniq)
            print(f"group {g:3d}  face {idx:4d}  n ({n[0]:+.3f},{n[1]:+.3f},{n[2]:+.3f})  {vs}")
        sys.stdout.flush()

    occt._group_planes = probe
    with tempfile.TemporaryDirectory() as d:
        sys.argv = ["brick-icons", a.part, "--engine", "occt", "--format", "svg",
                    "--out", d, *extra]
        cli.main()


if __name__ == "__main__":
    main()
