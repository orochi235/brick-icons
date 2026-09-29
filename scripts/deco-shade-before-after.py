"""One sheet: printed parts drawn with their decoration flat (before) and
shaded like the surface under it (after), both from THIS tree.

    .venv/bin/python scripts/deco-shade-before-after.py --out out/deco-shade.png \
        2552p01 3941p01:translucent-occt --zoom 0.35,0.3,0.3

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. `before`
disarms shade._deco_shade in-process, so nothing is stashed or checked out.
`--zoom FX,FY,FW` adds a second row per part: the panels cropped to the box
at (FX, FY) of width FW, as fractions of the drawing, rasterized finer -- a
baseplate's studs are a few pixels each at sheet size. Rasterized by resvg.
Writes <out>.json with each row's changed-component count, and keeps both
drawings of every part under <out without suffix>/.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from brick_icons import cli, db, shade
from _sheet import diff_panel, sheet

W = 420


def render(part, slot, out_dir, before):
    saved = shade._deco_shade
    if before:
        shade._deco_shade = lambda *a, **k: None
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        shade._deco_shade = saved
    name = Path(part).stem if part.endswith((".dat", ".ldr")) else part
    return out_dir / f"{name}.svg"


def raster(svg, width, box=None):
    png = svg.with_name(f"{svg.stem}-{width}.png")
    subprocess.run(["resvg", "-w", str(width), "--background", "white",
                    str(svg), str(png)], check=True)
    im = Image.open(png).convert("RGB")
    if box is None:
        return im
    fx, fy, fw = box
    x0, y0 = int(fx * im.width), int(fy * im.height)
    side = int(fw * im.width)
    return im.crop((x0, y0, x0 + side, y0 + int(side * 0.66))).resize(
        (W, int(W * 0.66)), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/deco-shade.png")
    ap.add_argument("--zoom", type=lambda s: tuple(map(float, s.split(","))))
    ap.add_argument("--title", default="printing: before = flat in its own "
                    "color, after = shaded like the surface under it")
    a = ap.parse_args()
    rows, counts = [], {}
    # the drawings stay beside the sheet, so a zoom can be re-cut without
    # re-rendering; the sheet's own directory bounds them
    keep = Path(a.out).with_suffix("")
    for i, spec in enumerate(a.parts, 1):
        part, _, slot = spec.partition(":")
        slot = slot or "occt"
        sb = render(part, slot, keep / f"before-{i}", True)
        sa = render(part, slot, keep / f"after-{i}", False)
        same = sb.read_bytes() == sa.read_bytes()
        b, n = raster(sb, W), raster(sa, W)
        rows.append((f"{part}\n{slot}", b, n))
        comps = diff_panel(b, n)[1]
        counts[spec] = {"svg_identical": same, "components": comps}
        if a.zoom:
            zb, zn = (raster(s, 4 * W, a.zoom) for s in (sb, sa))
            rows.append((f"{part}\n{slot}\nzoom", zb, zn))
            counts[spec]["zoom_components"] = diff_panel(zb, zn)[1]
        print(f"[{i}/{len(a.parts)}] {part} {slot} "
              f"{'identical' if same else f'{comps} changed regions'}",
              flush=True)
    sheet(a.title, rows, out=a.out)
    Path(a.out).with_suffix(".json").write_text(json.dumps(counts, indent=1))
    print(a.out)


if __name__ == "__main__":
    main()
