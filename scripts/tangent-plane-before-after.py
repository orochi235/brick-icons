"""One sheet: occt-slot drawings before and after a plane absorbed into a
tangent wall's fill takes its coplanar group siblings along
(occt._absorb_tangent_planes), both from THIS tree.

`before` sets occt.TANGENT_PLANE_GROUPS off in-process; nothing is stashed.
Prints each part's changed-component count as it finishes.

    .venv/bin/python scripts/tangent-plane-before-after.py --out out/tp.png 4079
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from brick_icons import cli, occt  # noqa: E402
from brick_icons.caption import Shot  # noqa: E402
from _sheet import components, changed  # noqa: E402
from _sheet import sheet  # noqa: E402

from brick_icons import db  # noqa: E402

SLOT = "occt"


def render(part, out_dir, before, width):
    saved = occt.TANGENT_PLANE_GROUPS
    occt.TANGENT_PLANE_GROUPS = not before
    try:
        args = cli._parse_args(db.canonical_argv(part, SLOT))
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        occt.TANGENT_PLANE_GROUPS = saved
    svg, png = out_dir / f"{part}.svg", out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(width), str(svg), str(png)], check=True)
    return Shot.of(Image.open(png).convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/tangent-plane.png")
    ap.add_argument("--width", type=int, default=420)
    ap.add_argument("--crop", type=int, default=0, metavar="PAD",
                    help="cut each row to the changed pixels plus PAD px")
    ap.add_argument("--title", default="occt slot: before / after a plane "
                    "tangent to a wall takes its coplanar faces into the wall's fill")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, part in enumerate(a.parts, 1):
            try:
                b = render(part, Path(td) / f"before-{i}", True, a.width)
                n = render(part, Path(td) / f"after-{i}", False, a.width)
            except Exception as e:      # one bad part must not sink the sheet
                print(f"[{i}/{len(a.parts)}] {part} ERROR {e}", flush=True)
                continue
            mask = changed(b.image, n.image)
            comps = components(mask)
            if a.crop and mask.any():
                ys, xs = np.nonzero(mask)
                box = (max(0, xs.min() - a.crop), max(0, ys.min() - a.crop),
                       xs.max() + a.crop, ys.max() + a.crop)
                b = Shot(b.image.crop(box), b.part, b.nbytes, b.secs)
                n = Shot(n.image.crop(box), n.part, n.nbytes, n.secs)
            rows.append((part, b, n))
            print(f"[{i}/{len(a.parts)}] {part} {comps} comp", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet(a.title, rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
