"""One sheet: parts drawn with stud instancing off and on, both from THIS tree.

    .venv/bin/python scripts/instancing-ab.py --out out/instancing-ab 51542 3404ec01:white-occt

A part is `<id>` or `<id>:<slot>`; the slot defaults to occt. `before` is the
slot's canonical argv plus `--stud-instancing off`, `after` the argv as the
slot runs it. Each row also reports the fill paths' sampled runs
(scripts/sampled-fill-runs.py), so an arc loss shows even when no pixel moves.
SVGs and PNGs are kept under --out beside sheet.png.
"""
import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from PIL import Image  # noqa: E402

from brick_icons import cli, db  # noqa: E402
from brick_icons.caption import Shot  # noqa: E402
from _sheet import sheet  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "sampled_fill_runs", ROOT / "scripts" / "sampled-fill-runs.py")
sfr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sfr)

W = 420


def render(part, slot, out_dir, extra):
    out_dir.mkdir(parents=True, exist_ok=True)
    args = cli._parse_args([*db.canonical_argv(part, slot), *extra])
    t0 = time.perf_counter()
    cli.process_one(cli._config_from_args(args), part, out_dir)
    secs = time.perf_counter() - t0
    svg = out_dir / f"{part}.svg"
    png = out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(W), str(svg), str(png)], check=True)
    worst = max((r for *_, r, _s in sfr.runs(svg.read_text())), default=0)
    return Shot.of(Image.open(png).convert("RGB"), part, svg, secs), worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", default="out/instancing-ab")
    ap.add_argument("--title", default="stud instancing: off (before) vs on (after, the default)")
    a = ap.parse_args()
    out = Path(a.out)
    rows = []
    for i, spec in enumerate(a.parts, 1):
        part, _, slot = spec.partition(":")
        slot = slot or "occt"
        b, wb = render(part, slot, out / f"{part}-{slot}-off", ["--stud-instancing", "off"])
        n, wn = render(part, slot, out / f"{part}-{slot}-on", [])
        rows.append((f"{part}\n{slot}\nrun {wb}->{wn}", b, n))
        print(f"[{i}/{len(a.parts)}] {part} {slot}  worst sampled run "
              f"off {wb:3d}  on {wn:3d}", flush=True)
    sheet(a.title, rows, columns=("instancing off", "instancing on"),
          out=out / "sheet.png")
    print(out / "sheet.png")


if __name__ == "__main__":
    main()
