"""One sheet: a fitted-limb fix's drawings before and after, both from THIS
tree -- `--flag` names the quadric constant turned off for `before` (default
LIMB_SKIPS_OWN_FACETS); nothing is stashed.

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. Prints each
row's changed-component count as it finishes.

    .venv/bin/python scripts/limb-surface-before-after.py --out out/limb.png \\
        20401 20401:naive 51283
"""
import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from brick_icons import cli, db, quadric  # noqa: E402
from brick_icons.caption import Shot  # noqa: E402
from _sheet import changed, components, sheet  # noqa: E402


def render(part, slot, out_dir, before, width, flag):
    saved = getattr(quadric, flag)
    setattr(quadric, flag, not before)
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        setattr(quadric, flag, saved)
    svg, png = out_dir / f"{part}.svg", out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(width), "--background", "white",
                    str(svg), str(png)], check=True)
    return Shot.of(Image.open(png).convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/limb-surface.png")
    ap.add_argument("--width", type=int, default=420)
    ap.add_argument("--flag", default="LIMB_SKIPS_OWN_FACETS")
    ap.add_argument("--title", default="before / after: a fitted limb's "
                    "visibility test skips the surface's own facets")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            try:
                b = render(part, slot, Path(td) / f"before-{i}", True, a.width, a.flag)
                n = render(part, slot, Path(td) / f"after-{i}", False, a.width, a.flag)
            except Exception as e:      # one bad part must not sink the sheet
                print(f"[{i}/{len(a.parts)}] {spec} ERROR {e}", flush=True)
                continue
            comps = components(changed(b.image, n.image))
            rows.append((f"{part}\n{slot}", b, n))
            print(f"[{i}/{len(a.parts)}] {spec} {comps} comp", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet(a.title, rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
