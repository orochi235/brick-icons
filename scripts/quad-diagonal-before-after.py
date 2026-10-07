"""One sheet: occt outline-flat3 drawings before and after an authored quad's
diagonal counts as a declared seam in occt._group_planes, both from THIS tree.

`before` sets occt.QUAD_DIAGONAL_SEAMS off in-process; nothing is stashed.
Prints each part's changed-component count as it finishes.

    .venv/bin/python scripts/quad-diagonal-before-after.py --out out/qd.png 32062 3705
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

from PIL import Image  # noqa: E402

from brick_icons import cli, occt  # noqa: E402
from brick_icons.caption import Shot  # noqa: E402
from _sheet import components, changed  # noqa: E402
from _sheet import sheet  # noqa: E402

ARGS = ["--engine", "occt", "--format", "svg", "--shading", "outline",
        "--shade-style", "flat3"]


def render(part, out_dir, before, width):
    saved = occt.QUAD_DIAGONAL_SEAMS
    occt.QUAD_DIAGONAL_SEAMS = not before
    try:
        args = cli._parse_args([part, *ARGS])
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        occt.QUAD_DIAGONAL_SEAMS = saved
    svg, png = out_dir / f"{part}.svg", out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(width), str(svg), str(png)], check=True)
    return Shot.of(Image.open(png).convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/quad-diagonal.png")
    ap.add_argument("--width", type=int, default=420)
    ap.add_argument("--title", default="occt outline-flat3: before / after "
                    "a quad's diagonal joins its halves' shading group")
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
            comps = components(changed(b.image, n.image))
            rows.append((part, b, n))
            print(f"[{i}/{len(a.parts)}] {part} {comps} comp", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet(a.title, rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
