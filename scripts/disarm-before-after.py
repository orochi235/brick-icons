"""One sheet: parts drawn with a fix disarmed (before) and as the tree stands
(after), both from THIS tree -- nothing is stashed or checked out.

    .venv/bin/python scripts/disarm-before-after.py --out out/x.png \\
        --set occt.TANGENT_PLANE_GROUPS=False 4079 4079:white-occt

`--set module.NAME=EXPR` (repeatable) is applied for `before` only; EXPR is a
Python expression evaluated with the module's namespace, so a function can be
swapped too: `--set "process.seam_px=lambda *a, **k: SEAM_PX"`. A part is
`<id>` or `<id>:<slot>` (default occt). A fix behind a CLI flag is disarmed
with `--before-args "--deco-shade off"` instead, appended to the slot's argv.
Prints each row's changed-component count as it finishes.
"""
import argparse
import importlib
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

from brick_icons import cli, db  # noqa: E402
from _sheet import changed, components, sheet  # noqa: E402


def parse_sets(sets):
    out = []
    for s in sets:
        target, _, expr = s.partition("=")
        mod_name, _, name = target.rpartition(".")
        mod = importlib.import_module(f"brick_icons.{mod_name}")
        if not hasattr(mod, name):
            raise SystemExit(f"brick_icons.{mod_name} has no {name}")
        out.append((mod, name, eval(expr, vars(mod))))
    return out


def render(part, slot, out_dir, sets, width, extra=()):
    saved = [(m, n, getattr(m, n)) for m, n, _v in sets]
    for m, n, v in sets:
        setattr(m, n, v)
    try:
        args = cli._parse_args([*db.canonical_argv(part, slot), *extra])
        cli.process_one(cli._config_from_args(args), part, out_dir)
    finally:
        for m, n, v in saved:
            setattr(m, n, v)
    svg, png = out_dir / f"{part}.svg", out_dir / f"{part}.png"
    subprocess.run(["resvg", "-w", str(width), "--background", "white",
                    str(svg), str(png)], check=True)
    return Image.open(png).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--set", dest="sets", action="append", default=[])
    ap.add_argument("--before-args", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--width", type=int, default=480)
    a = ap.parse_args()
    if not a.sets and not a.before_args:
        ap.error("give --set or --before-args: nothing would differ")
    sets = parse_sets(a.sets)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for i, spec in enumerate(a.parts, 1):
            part, _, slot = spec.partition(":")
            slot = slot or "occt"
            try:
                b = render(part, slot, Path(td) / f"b{i}", sets, a.width,
                           shlex.split(a.before_args))
                n = render(part, slot, Path(td) / f"a{i}", [], a.width)
            except Exception as e:      # one bad part must not sink the sheet
                print(f"[{i}/{len(a.parts)}] {spec} ERROR {e}", flush=True)
                continue
            rows.append((f"{part}\n{slot}", b, n))
            print(f"[{i}/{len(a.parts)}] {spec} "
                  f"{components(changed(b, n))} comp", flush=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    sheet(a.title, rows, columns=("before (fix disarmed)", "after (HEAD)"),
          out=a.out)
    print(a.out)


if __name__ == "__main__":
    main()
