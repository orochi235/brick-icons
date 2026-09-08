"""What each render mode costs, on one sample of parts run through all of them.

Same part set for every mode, so the comparison is within-part. The census's own
setting is outline+flat3; the others have never been costed.
"""
import json, sys, time, glob, importlib.util, tempfile, argparse, subprocess
from pathlib import Path
import numpy as np
from PIL import Image
# cel at zoom 8 rasterizes to ~209 megapixels, over PIL's 179 MP bomb guard.
# The size is the finding, not an attack.
Image.MAX_IMAGE_PIXELS = None
from brick_icons import cli

spec = importlib.util.spec_from_file_location("cst", "scripts/compare-silhouette-truth.py")
cst = importlib.util.module_from_spec(spec); spec.loader.exec_module(cst)

ENGINE, ZOOM = "naive", 8
# `normal` is dropped: the CLI refuses to emit SVG for it ("--shading must be
# outline or cel"), so it is not a mode this pipeline can cost.
MODES = [(sh, st) for sh in ("cel", "outline") for st in ("none", "flat3")]
# Bounded sample: every part runs six times, so the slow tail is left out on
# purpose — this measures the mode ratio, not the corpus.
BANDS = [(0, 2, 2), (2, 5, 2), (5, 15, 3), (15, 40, 2), (40, 90, 1)]

by_secs = {}
for f in glob.glob(f"out/census-run1/{ENGINE}-*.jsonl"):
    for line in open(f, errors="ignore"):
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except json.JSONDecodeError: continue
        if "error" in d or d.get("secs") is None: continue
        by_secs.setdefault(d["part"], d["secs"])

sample = []
for lo, hi, n in BANDS:
    pool = sorted(p for p, s in by_secs.items() if lo <= s < hi)
    step = max(1, len(pool) // n)
    sample += [(p, by_secs[p]) for p in pool[::step][:n]]

total_runs = len(sample) * len(MODES)
print(f"{len(sample)} parts x {len(MODES)} modes = {total_runs} runs", flush=True)

out_path = Path(sys.argv[1])
rows, i = [], 0
for part, prior in sample:
    for shading, style in MODES:
        i += 1
        try:
            with tempfile.TemporaryDirectory() as td:
                tmp = Path(td)
                argv = [part, "--format", "svg", "--shading", shading,
                        "--shade-style", style, "--angle", "iso", "--engine", ENGINE,
                        "--line-width", "0", "--silhouette-width", "0", "--out", str(tmp)]
                parsed = cli.build_parser().parse_args(argv)
                cfg = cli._config_from_args(parsed)
                t0 = time.perf_counter()
                cli.process_one(cfg, part, tmp)
                render = time.perf_counter() - t0

                t0 = time.perf_counter()
                svg, png = tmp / f"{part}.svg", tmp / f"{part}.png"
                subprocess.run(["resvg", "--zoom", str(ZOOM), str(svg), str(png)],
                               check=True, capture_output=True)
                _ = np.array(Image.open(png).convert("RGBA"))[:, :, 3] > 128
                raster = time.perf_counter() - t0
                svg_bytes = svg.stat().st_size
            rows.append({"part": part, "prior_secs": prior, "shading": shading,
                         "style": style, "render": round(render, 3),
                         "rasterize": round(raster, 3), "svg_bytes": svg_bytes})
            print(f"  {i}/{total_runs} {part} {shading}+{style}: "
                  f"render {render:.2f}s raster {raster:.2f}s svg {svg_bytes/1024:.0f}K", flush=True)
        except BaseException as e:
            print(f"  {i}/{total_runs} {part} {shading}+{style}: FAILED "
                  f"{type(e).__name__}: {str(e)[:70]}", flush=True)
        out_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print("wrote", out_path, flush=True)
