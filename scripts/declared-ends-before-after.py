"""One sheet: parts drawn with and without the orphan cull's declared-end
anchors (hlr._declared_ends), both from THIS tree.

    .venv/bin/python scripts/declared-ends-before-after.py --out out/de.png \
        24434 3001:white-occt

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. `before`
disarms the anchors in-process, so nothing is stashed. Rasterized by resvg
at --width; prints each part's changed-component count as it goes.
"""
import argparse
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image

from brick_icons import cli, db, hlr
from brick_icons.caption import Shot
from _sheet import changed, components, sheet

MANIFEST = Path(__file__).resolve().parent.parent / "tests/goldens/manifest.toml"


def render(part, slot, out_dir, before, width):
    saved = hlr._declared_ends
    if before:
        hlr._declared_ends = lambda *a, **k: None
    try:
        args = cli._parse_args(db.canonical_argv(part, slot))
        t0 = time.perf_counter()
        cli.process_one(cli._config_from_args(args), part, out_dir)
        secs = time.perf_counter() - t0
    finally:
        hlr._declared_ends = saved
    svg = out_dir / f"{part}.svg"
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(width), str(svg), str(png)], check=True)
    im = Image.open(png).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    return Shot.of(flat.convert("RGB"), part, svg, secs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--goldens", action="append", default=[],
                    metavar="LIST:SLOT",
                    help="every part of a tests/goldens/manifest.toml list "
                         "in a slot, e.g. unprinted:white-occt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="orphan cull: before (no declared-end "
                                       "anchors) vs after (declared arc ends "
                                       "anchor a tip)")
    ap.add_argument("--width", type=int, default=600)
    ap.add_argument("--moved-only", action="store_true",
                    help="sheet only the parts that changed")
    a = ap.parse_args()
    for spec in a.goldens:
        name, _, slot = spec.partition(":")
        parts = tomllib.loads(MANIFEST.read_text())["parts"][name]
        a.parts += [f"{p}:{slot}" for p in parts]
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            try:
                b = render(part, slot, Path(td) / f"before-{i}", True, a.width)
                n = render(part, slot, Path(td) / f"after-{i}", False, a.width)
            except Exception as e:                       # noqa: BLE001
                print(f"[{i}/{len(a.parts)}] {part} {slot} ERROR {e}",
                      flush=True)
                continue
            comps = components(changed(b.image, n.image))
            if comps or not a.moved_only:
                rows.append((f"{part}\n{slot}", b, n))
            print(f"[{i}/{len(a.parts)}] {part} {slot} {comps} comp",
                  flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print("nothing moved; no sheet")
        return
    sheet(a.title, rows, out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
