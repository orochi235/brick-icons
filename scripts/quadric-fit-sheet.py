"""Before/after/diff sheet for the fitted-quadric shading, both sides from
THIS tree, with LDView's gray reference beside each row.

    .venv/bin/python scripts/quadric-fit-sheet.py --out out/quadric.png \\
        51283 32474 2736:naive

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. `before` sets
quadric.ARMED False in-process, so every declared-smooth region is shaded
by its normals and outlined by its facets, as before any quadric was fitted.
Rasterized by resvg on white.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from brick_icons import cli, db, quadric  # noqa: E402
from _sheet import sheet  # noqa: E402

W = 360


def _white(im):
    im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    return bg.convert("RGB")


def render(part, slot, out_dir, before):
    saved = quadric.ARMED
    quadric.ARMED = not before
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        quadric.ARMED = saved
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(W), "--background", "white",
                    str(out_dir / f"{part}.svg"), str(png)], check=True)
    return _white(Image.open(png))


def reference(part, out_dir, size, refs=None):
    """LDView's gray reference: drawn here, or read from `refs` (a directory
    of <part>.webp) on a node that has no LDView."""
    if refs is not None:
        src = Path(refs) / f"{part}.webp"
        if not src.exists():
            return Image.new("RGB", size, "white")
    else:
        args = cli._parse_args(db.canonical_argv(part, "reference-gray"))
        cli.process_one(cli._config_from_args(args), part, out_dir)
        src = out_dir / f"{part}.webp"
    im = _white(Image.open(src))
    im.thumbnail(size)
    return im


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/quadric-sheet.png")
    ap.add_argument("--refs", help="directory of LDView <part>.webp to use "
                    "instead of drawing them (a node without LDView)")
    ap.add_argument("--title", default="fitted-quadric shading: before "
                    "(normals only) vs after (sphere/ellipsoid/cone fit)")
    a = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            b = render(part, slot, Path(td) / f"before-{i}", True)
            n = render(part, slot, Path(td) / f"after-{i}", False)
            ref = reference(part, Path(td) / f"ref-{i}", n.size, a.refs)
            rows.append((f"{part}\n{slot}", b, n, ref))
            print(f"[{i}/{len(a.parts)}] {part} {slot}", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet(a.title, rows, out=a.out, extra="LDView gray")
    print(a.out)


if __name__ == "__main__":
    main()
