#!/usr/bin/env python3
"""Write the repaired triangle mesh the engine is given, as OBJ, one file per part.

    python scripts/export-mesh.py --out /tmp/meshes 50950 4740p03

This is the input side of the pipeline, not its output: it answers "is the
geometry already wrong before hidden-line removal touched it", which a render
cannot distinguish from an occlusion bug. `--report` adds the counts that
usually settle it -- unpaired edges are sewing cracks, and a mesh with none
still rendering wrong puts the fault after this stage.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import hlr  # noqa: E402


def repaired(part: str, ldraw_dir: Path) -> np.ndarray:
    from brick_icons import repair
    roots = hlr.default_roots(ldraw_dir)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3), out, roots)
    if not out["tri"]:
        return np.zeros((0, 3, 3))
    return np.asarray(repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                           hlr.MESH_CACHE_DIR), float)


def write_obj(tris: np.ndarray, path: Path) -> None:
    with path.open("w") as fh:
        fh.write(f"# {len(tris)} triangles, repaired mesh stage\n")
        for t in tris:
            for v in t:
                fh.write("v %.6f %.6f %.6f\n" % tuple(v))
        for i in range(len(tris)):
            fh.write("f %d %d %d\n" % (3 * i + 1, 3 * i + 2, 3 * i + 3))


def edge_report(tris: np.ndarray) -> str:
    """Unpaired edges are where sewing has nothing to stitch to."""
    counts = Counter()
    for t in tris:
        k = [tuple(np.round(v, 3)) for v in t]
        for a, b in ((k[0], k[1]), (k[1], k[2]), (k[2], k[0])):
            counts[(a, b) if a <= b else (b, a)] += 1
    hist = Counter(counts.values())
    unpaired = hist.get(1, 0)
    return (f"{len(tris)} tris, {len(counts)} distinct edges, "
            f"{unpaired} unpaired, multiplicity {dict(sorted(hist.items()))}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", type=Path, default=Path("."))
    ap.add_argument("--root", type=Path, default=Path("vendor/ldraw"))
    ap.add_argument("--report", action="store_true",
                    help="print edge pairing counts instead of only writing")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(args.parts, 1):
        tris = repaired(part, args.root)
        dest = args.out / f"{part}.obj"
        write_obj(tris, dest)
        note = f"  {edge_report(tris)}" if args.report else ""
        print(f"{i}/{len(args.parts)} {part} -> {dest}{note}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
