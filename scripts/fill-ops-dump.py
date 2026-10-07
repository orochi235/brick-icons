"""Draw parts in a golden combo and keep what fill_ops was given and returned,
so a pixel of the SVG can be traced to the face that painted it.

    .venv/bin/python scripts/fill-ops-dump.py --out out/dump 3649 4070
    .venv/bin/python scripts/fill-ops-dump.py --out out/dump \
        --set shade.ABUT_TIES_ONLY=False 3649

Writes `<out>/<part>.svg`, `.png` (resvg, --px wide, when resvg is on PATH), `.fit.json` and
`.fill.pkl`: {"faces": [...], "ops": [...]} with each face reduced to its
plain-data keys (callables dropped). `--set` assigns a module attribute
before drawing; the value is a Python literal.
"""
import argparse
import ast
import importlib
import pickle
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tomllib  # noqa: E402

from brick_icons import cli, shade  # noqa: E402


def plain(v):
    if callable(v):
        return None
    if isinstance(v, dict):
        return {k: plain(x) for k, x in v.items() if not callable(x)}
    if isinstance(v, (list, tuple)):
        return type(v)(plain(x) for x in v) if isinstance(v, list) else tuple(plain(x) for x in v)
    try:
        pickle.dumps(v)
        return v
    except Exception:
        return repr(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--combo", default="outline-flat3")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--px", type=int, default=512)
    ap.add_argument("--set", action="append", default=[], dest="sets")
    a = ap.parse_args()
    for s in a.sets:
        lhs, rhs = s.split("=", 1)
        mod, attr = lhs.rsplit(".", 1)
        setattr(importlib.import_module(f"brick_icons.{mod}"), attr,
                ast.literal_eval(rhs))
    combo = tomllib.loads((ROOT / "tests/goldens/manifest.toml").read_text())
    args = combo["combo"][a.combo]["args"]
    real = shade.fill_ops
    seen = {}

    def spy(faces, *pa, **kw):
        ops = real(faces, *pa, **kw)
        seen["faces"] = [plain(f) for f in faces]
        seen["ops"] = plain(ops)
        return ops

    shade.fill_ops = spy
    a.out.mkdir(parents=True, exist_ok=True)
    for k, part in enumerate(a.parts, 1):
        seen.clear()
        t0 = time.perf_counter()
        cfg = cli._config_from_args(cli._parse_args(
            [part, "--engine", a.engine, *args]))
        cli.process_one(cfg, part, a.out)
        (a.out / f"{part}.fill.pkl").write_bytes(pickle.dumps(dict(seen)))
        if shutil.which("resvg"):
            subprocess.run(["resvg", "--width", str(a.px), str(a.out / f"{part}.svg"),
                            str(a.out / f"{part}.png")], check=True)
        print(f"{k}/{len(a.parts)} {part} {time.perf_counter() - t0:.1f}s",
              flush=True)


main()
