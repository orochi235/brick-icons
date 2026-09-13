#!/usr/bin/env python3
"""Does a render's silhouette sit where the part's own polygons project?

    python scripts/compare-silhouette-truth.py 3941 --angle 30,65 --out /tmp/sil.json

Answers "is this outline feature real geometry or something the pipeline
invented", which eyeballing a render cannot. The reference is the .dat's own
triangles under the render's own camera (read from the emitted `.fit.json`),
rasterized independently of HLR, fills and booleans -- so a disagreement is
the pipeline's, not the loader's.

Reports MISSING (part the render omits) and EXTRA (render beyond the part) as
component counts, and the EXTRA distance percentiles. Read those percentiles,
not the pixel total: a correct render is uniformly ~half a stroke wide outside
the hard-edged reference from antialiasing and from arcs bulging past the
chords they replace, which is a large area at a small distance. A real defect
is a few px of distance somewhere.

Two traps this exists to avoid:
  - Primitive substitution. `flatten` only records a Cylinder/Disc/Ring
    analytically when `out` carries an "analytic" key; without one it recurses
    into the primitive file and tessellates. The reference needs the second,
    or it is full of holes where every curved surface should be.
  - LDView is NOT usable as the reference here. Its `-DefaultLatLong`
    latitude does not agree with `view_basis`'s -- at "30,65" it returns a
    silhouette of aspect 1.08 against our 0.91 -- so an overlay compares two
    different poses and invents disagreements everywhere.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, hlr, timing
from brick_icons import build
from brick_icons.batch import Runner


def truth_mask(part: str, ldraw_dir: Path, fit: dict, zoom: int,
               pose=None) -> np.ndarray:
    """The part's own triangles, projected and filled. No "analytic" key, so
    every primitive tessellates instead of being recognized.

    `pose` has to be the same turn the render used. Left at identity against a
    posed render the oracle draws a different part, and the two disagree over
    the whole silhouette -- 27,785 missing pixels on 2362a against 2.
    """
    right, up = np.array(fit["right"]), np.array(fit["up"])
    k, kx, ky = fit["k"], fit["kx"], fit["ky"]
    W, H = fit["width"] * zoom, fit["height"] * zoom

    roots = hlr.default_roots(ldraw_dir)
    out: dict = {"2": [], "5": [], "tri": [], "tri_meta": []}
    root = np.eye(3) if pose is None else np.asarray(pose, float)
    hlr.flatten(hlr._resolve_input(part, roots), root, np.zeros(3), out, roots)
    T = np.array(out["tri"], float)
    P = np.stack([(T @ right) * k * zoom + kx * zoom,
                  -(T @ up) * k * zoom + ky * zoom], axis=-1)

    mask = np.zeros((H, W), bool)
    for tri in P:
        y0 = max(0, int(np.floor(tri[:, 1].min())))
        y1 = min(H - 1, int(np.ceil(tri[:, 1].max())))
        for y in range(y0, y1 + 1):
            yc, xs = y + 0.5, []
            for i in range(3):
                a, b = tri[i], tri[(i + 1) % 3]
                if (a[1] <= yc) != (b[1] <= yc):
                    xs.append(a[0] + (yc - a[1]) * (b[0] - a[0]) / (b[1] - a[1]))
            if len(xs) < 2:
                continue
            i0 = max(0, int(np.ceil(min(xs) - 0.5)))
            i1 = min(W - 1, int(np.floor(max(xs) - 0.5)))
            if i1 >= i0:
                mask[y, i0:i1 + 1] = True
    return mask


def components(m: np.ndarray, zoom: int, floor_px: int):
    lab, n = ndimage.label(m)
    if not n:
        return []
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    out = []
    for idx, s in sorted(enumerate(sizes, 1), key=lambda kv: -kv[1]):
        if s < floor_px:
            break
        ys, xs = np.nonzero(lab == idx)
        out.append({"px": int(s),
                    "x": [round(xs.min() / zoom, 1), round(xs.max() / zoom, 1)],
                    "y": [round(ys.min() / zoom, 1), round(ys.max() / zoom, 1)]})
    return out


def ink_mask(rgba: np.ndarray, opacity: float | None) -> np.ndarray:
    """Which pixels the render drew, at the antialias midpoint of its own fills.

    The midpoint scales with the fill opacity or it stops being a midpoint: a
    surface drawn at 0.5 rasterizes to alpha 128, so an absolute `> 128` reads
    every single-layer region as undrawn and passes only where two surfaces
    overlap. Solid slots pass opacity None and keep the old threshold exactly.
    """
    return rgba[:, :, 3] > 128 * (1.0 if opacity is None else opacity)


def drawn_as(args) -> dict:
    """What this run drew, as the fields every row carries. One definition:
    three sites build these rows and a field added to two of them says
    nothing about the third's."""
    fields = {"style": args.shade_style,
              "strokes": [args.line_width, args.silhouette_width]}
    if args.opacity is not None:
        fields["opacity"] = args.opacity
    return fields


def one(part: str, args, tmp: Path) -> dict:
    """Render and compare against the reference.

    Strokeless by default: the fills carry the silhouette and there is no
    stroke overhang to subtract. With --line-width/--silhouette-width above 0
    the strokes sit ~half their width outside the fill boundary, so EXTRA
    grows by a band everywhere and its distance percentiles are no longer
    comparable to a strokeless run's."""
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", args.shade_style, "--angle", args.angle,
            "--engine", args.engine, "--line-width", str(args.line_width),
            "--silhouette-width", str(args.silhouette_width),
            *(["--opacity", str(args.opacity)] if args.opacity is not None else []),
            "--out", str(tmp)]
    parsed = cli.build_parser().parse_args(argv)
    cfg = cli._config_from_args(parsed)
    # Timed per phase, because `secs` alone cannot say whether a slow part is
    # slow to draw or slow to build a reference for, and those have different
    # fixes.
    phase = {}
    timing.reset()
    with timing.phase("render"):
        cli.process_one(cfg, part, tmp)
    # Paths, not names: `render/geometry/engine/hlr` says where in the render
    # the time went and at what depth. A parent's time includes its children,
    # so what a level does not name is its own leftover -- for `render` that
    # is the SVG emit.
    phase.update(timing.phases())

    t0 = time.perf_counter()
    svg, png = tmp / f"{part}.svg", tmp / f"{part}.png"
    subprocess.run(["resvg", "--zoom", str(args.zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    ours = ink_mask(np.array(Image.open(png).convert("RGBA")), args.opacity)
    phase["rasterize"] = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    truth = truth_mask(part, cfg.ldraw_dir,
                       json.loads((tmp / f"{part}.fit.json").read_text()),
                       args.zoom, pose=cli.part_pose(cfg, part))
    phase["truth_mask"] = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    extra, missing = ours & ~truth, truth & ~ours
    dist = ndimage.distance_transform_edt(~truth)
    pct = {str(p): round(float(np.percentile(dist[extra], p)) / args.zoom, 2)
           for p in (50, 90, 99, 100)} if extra.any() else {}
    row = {"part": part, "engine": args.engine, "angle": args.angle,
           **drawn_as(args),
           "extra_px": int(extra.sum()), "missing_px": int(missing.sum()),
           "extra_dist_px": pct,
           "missing": components(missing, args.zoom, args.floor),
           "extra": components(extra, args.zoom, args.floor)}
    phase["compare"] = round(time.perf_counter() - t0, 2)
    row["phase"] = phase
    # Facts about the render that are not times -- a kernel call the engine
    # had to work around still took seconds, so no phase can carry one.
    if timing.counts():
        row["counts"] = timing.counts()
    return row


def _bare(part: str, work, args) -> dict:
    """The same row a Runner would build, for a run with no --jsonl behind it."""
    t0 = time.time()
    try:
        r = work(part)
    except BaseException as exc:  # a part must not end the run
        r = {"part": part, "engine": args.engine, "angle": args.angle,
             **drawn_as(args), "build": build(),
             "error": type(exc).__name__, "detail": str(exc)[:300],
             "traceback": traceback.format_exc()[-1200:]}
    r["secs"] = round(time.time() - t0, 1)
    r.setdefault("build", build())   # Runner's `extra` merge, which this path skips
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--shade-style", dest="shade_style", default="flat3",
                    help="fill treatment; 'white' draws every body surface "
                         "one opaque white, so the strokes carry the drawing")
    ap.add_argument("--line-width", dest="line_width", type=int, default=0,
                    help="interior stroke, output px (0 = strokeless oracle)")
    ap.add_argument("--opacity", type=float,
                    help="face-fill opacity for the translucent slots. The "
                         "far side draws INSIDE the silhouette, so it adds no "
                         "EXTRA: the row scores the outline, not the "
                         "translucency")
    ap.add_argument("--silhouette-width", dest="silhouette_width", type=int,
                    default=0, help="contour stroke, output px")
    ap.add_argument("--zoom", type=int, default=8, help="raster px per canvas px")
    ap.add_argument("--floor", type=int, default=200,
                    help="smallest diff component to report, in raster px")
    ap.add_argument("--out", help="write results as JSON here")
    ap.add_argument("--jsonl", help="append one result per line here, as it finishes")
    ap.add_argument("--skip-done", action="store_true",
                    help="with --jsonl, skip parts already in that file")
    ap.add_argument("--timeout", type=float, default=0,
                    help="seconds a single part may take (0 = no limit)")
    ap.add_argument("--no-isolate", dest="isolate", action="store_false",
                    help="render in this process. --timeout then cannot stop a "
                         "part that spends its life inside one OCP call, which "
                         "is what the slow ones do")
    ap.add_argument("--mem-gb", dest="mem_gb", type=float, default=8,
                    help="resident GB a single render may reach before it is "
                         "killed (0 = no limit)")
    ap.add_argument("--keep", metavar="DIR",
                    help="save every render and its camera under DIR/<engine>/, "
                         "so a finding can be looked at without re-rendering")
    ap.add_argument("--bury", action="store_true",
                    help="with --jsonl, record whatever the last run left "
                         "in-flight as ProcessDied and exit, rendering nothing")
    args = ap.parse_args()

    # `build` names the engine revision that drew the row. A census tree is
    # merged from many passes on several machines, and the ingest can only
    # see its own checkout, so provenance has to be written where the render
    # happens or it is gone.
    extra = {"engine": args.engine, "angle": args.angle,
             **drawn_as(args), "build": build()}
    # A part the watchdog kills leaves .inflight behind with no row, and the
    # burial only happens on the way into a re-run of that same batch. Where
    # none comes, the part is in no census at all -- neither drawn nor failed,
    # just absent, and absent from a coverage list is absent from every retry.
    if args.bury:
        if not args.jsonl:
            ap.error("--bury needs --jsonl")
        Runner(args.jsonl, key="part", extra=extra).remaining([])
        return 0

    ids = args.parts
    if args.list:
        ids += [s for ln in Path(args.list).read_text().splitlines()
                if (s := ln.split("#")[0].strip())]
    if not ids:
        ap.error("name at least one part, or pass --list")

    runner = Runner(args.jsonl, timeout=args.timeout, key="part", extra=extra,
                    isolate=args.isolate,
                    mem_gb=args.mem_gb) if args.jsonl else None
    if runner and args.skip_done:
        before = len(ids)
        ids = runner.remaining(ids)
        print(f"resuming: {before - len(ids)} done, {len(ids)} left", flush=True)
        # Only this process knows the absolute denominator: remaining() dedupes
        # by key, so counting the JSONL overcounts a part that has a retry row.
        # census-shard.sh attaches the label; onto reads it as the unit's size.
        print(f"onto: plan {before - len(ids)}/{before}", flush=True)

    keep = Path(args.keep) if args.keep else None
    if keep:
        (keep / args.engine).mkdir(parents=True, exist_ok=True)

    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for n, pid in enumerate(ids, 1):
            def work(part, tmp=tmp):
                return one(part, args, tmp)
            r = runner.run(pid, work) if runner else _bare(pid, work, args)
            rows.append(r)
            if "error" in r:
                print(f"{n}/{len(ids)} {pid} {args.engine}@{args.angle}: "
                      f"FAILED {r['error']}: {r['detail'].splitlines()[0][:120]} "
                      f"[{r['secs']}s]", flush=True)
            else:
                print(f"{n}/{len(ids)} {pid} {args.engine}@{args.angle}: "
                      f"missing {r['missing_px']}px ({len(r['missing'])} comps), "
                      f"extra {r['extra_px']}px "
                      f"(99th {r['extra_dist_px'].get('99', 0)}px, "
                      f"max {r['extra_dist_px'].get('100', 0)}px) "
                      f"[{r['secs']}s]", flush=True)
            # Every render, not only the flagged ones. A flag is not a defect
            # -- `18742` measures 7.12px of stray ink under occt and 0.52px
            # under naive, because occt draws the exact circle the truth mask
            # only has as a 16-gon -- and nothing but the drawing tells the two
            # apart afterwards.
            if keep:
                for suffix in (".svg", ".fit.json"):
                    src = tmp / f"{pid}{suffix}"
                    if src.exists():
                        src.rename(keep / args.engine / f"{pid}{suffix}")
            for f in tmp.glob(f"{pid}.*"):
                f.unlink(missing_ok=True)
            if runner and runner.pruned():
                # onto records only the exit code, and 0 here means "did what
                # it was told" for a full run and a pruned one alike -- this
                # line is the only place the difference survives.
                print(f"pruned at {n}/{len(ids)} parts", flush=True)
                break
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
