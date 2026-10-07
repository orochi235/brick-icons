"""Which planar faces occt._group_planes unions, for faces inside a world box.

Wraps the grouping step of a real CLI render and prints, for every planar face
whose outer wire lies inside --box, its world normal, its vertices and the
group it was put in. Two facets of one smooth surface in different groups is
a tone step in the fill; this names the facets and the edge between them.

    .venv/bin/python scripts/probe-plane-groups.py 32062 --box 17,-7,-7,21,7,7 \\
        -- --shading outline --shade-style flat3
"""
import argparse
import sys
import tempfile
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
    ap.add_argument("--box", required=True, help="x0,y0,z0,x1,y1,z1 world LDU")
    a = ap.parse_args(argv)
    b = np.array([float(v) for v in a.box.split(",")]).reshape(2, 3)
    orig = occt._group_planes

    def probe(shape, out, plane_by_idx):
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
