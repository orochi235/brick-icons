"""Residual of every quadric model on each declared-smooth region of some
parts -- the measurement the gates in brick_icons/quadric.py are set from.

    .venv/bin/python scripts/measure-smooth-fit.py 51283 3960 4740

One line per region: facets, then sphere / ellipsoid / cone residual (RMS
distance over size; `-` where the model cannot be fitted), then what
quadric.classify decides.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import quadric  # noqa: E402

LDRAW = Path(__file__).resolve().parent.parent / "vendor/ldraw"


def fmt(r):
    return "      -" if r is None else f"{r[1]:7.4f}"


def main():
    parts = sys.argv[1:]
    print(f"{'part':>12} {'tris':>5} {'sphere':>7} {'ellips':>7} {'cone':>7}  class")
    for i, part in enumerate(parts, 1):
        regions = quadric.part_regions(part, LDRAW)
        for verts, normals in sorted(regions, key=lambda r: -len(r[0])):
            r = quadric.residuals(verts, normals)
            f = quadric.classify(verts, normals)
            print(f"{part:>12} {len(verts):5d} {fmt(r['sphere'])} "
                  f"{fmt(r['ellipsoid'])} {fmt(r['cone'])}  "
                  f"{f.kind if f else 'freeform'}", flush=True)
        if not regions:
            print(f"{part:>12}  (no region)", flush=True)
        print(f"# {i}/{len(parts)} {part}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
