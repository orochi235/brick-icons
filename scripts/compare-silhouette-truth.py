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
import signal
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

from brick_icons import cli, hlr


def truth_mask(part: str, ldraw_dir: Path, fit: dict, zoom: int) -> np.ndarray:
    """The part's own triangles, projected and filled. No "analytic" key, so
    every primitive tessellates instead of being recognized."""
    right, up = np.array(fit["right"]), np.array(fit["up"])
    k, kx, ky = fit["k"], fit["kx"], fit["ky"]
    W, H = fit["width"] * zoom, fit["height"] * zoom

    roots = hlr.default_roots(ldraw_dir)
    out: dict = {"2": [], "5": [], "tri": [], "tri_meta": []}
    hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3), out, roots)
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


def one(part: str, args, tmp: Path) -> dict:
    """Render strokeless (fills carry the silhouette, no stroke overhang to
    subtract) and compare against the reference."""
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", "flat3", "--angle", args.angle,
            "--engine", args.engine, "--line-width", "0",
            "--silhouette-width", "0", "--out", str(tmp)]
    parsed = cli.build_parser().parse_args(argv)
    cfg = cli._config_from_args(parsed)
    cli.process_one(cfg, part, tmp)

    svg, png = tmp / f"{part}.svg", tmp / f"{part}.png"
    subprocess.run(["resvg", "--zoom", str(args.zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    ours = np.array(Image.open(png).convert("RGBA"))[:, :, 3] > 128
    truth = truth_mask(part, cfg.ldraw_dir, json.loads((tmp / f"{part}.fit.json").read_text()),
                       args.zoom)

    extra, missing = ours & ~truth, truth & ~ours
    dist = ndimage.distance_transform_edt(~truth)
    pct = {str(p): round(float(np.percentile(dist[extra], p)) / args.zoom, 2)
           for p in (50, 90, 99, 100)} if extra.any() else {}
    return {"part": part, "engine": args.engine, "angle": args.angle,
            "extra_px": int(extra.sum()), "missing_px": int(missing.sum()),
            "extra_dist_px": pct,
            "missing": components(missing, args.zoom, args.floor),
            "extra": components(extra, args.zoom, args.floor)}


_ARMED = None


def _on_alarm(signum, frame):
    """Installed once and never removed: SIGALRM's default action is to KILL,
    so a timer that expires in the microseconds before the itimer is disarmed
    takes the whole run down silently. Ignoring a disarmed alarm is the fix."""
    if _ARMED:
        raise TimeoutError(f"exceeded {_ARMED}s")


def run_guarded(part: str, args, tmp: Path) -> dict:
    """`one()` under a wall-clock cap. Best effort: the alarm lands between
    Python bytecodes, so a part stuck inside a C call runs past it."""
    global _ARMED
    if not args.timeout:
        return one(part, args, tmp)
    _ARMED = args.timeout
    signal.setitimer(signal.ITIMER_REAL, args.timeout)
    try:
        return one(part, args, tmp)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        _ARMED = None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--engine", default="naive")
    ap.add_argument("--zoom", type=int, default=8, help="raster px per canvas px")
    ap.add_argument("--floor", type=int, default=200,
                    help="smallest diff component to report, in raster px")
    ap.add_argument("--out", help="write results as JSON here")
    ap.add_argument("--jsonl", help="append one result per line here, as it finishes")
    ap.add_argument("--skip-done", action="store_true",
                    help="with --jsonl, skip parts already in that file")
    ap.add_argument("--timeout", type=float, default=0,
                    help="seconds a single part may take (0 = no limit)")
    args = ap.parse_args()

    ids = args.parts
    if args.list:
        ids += [s for ln in Path(args.list).read_text().splitlines()
                if (s := ln.split("#")[0].strip())]
    if not ids:
        ap.error("name at least one part, or pass --list")

    jsonl = Path(args.jsonl) if args.jsonl else None
    if jsonl and args.skip_done and jsonl.exists():
        done = {json.loads(ln)["part"] for ln in jsonl.read_text().splitlines() if ln.strip()}
        ids = [i for i in ids if i not in done]
        print(f"resuming: {len(done)} done, {len(ids)} left", flush=True)

    if args.timeout:
        signal.signal(signal.SIGALRM, _on_alarm)

    inflight = Path(f"{args.jsonl}.inflight") if jsonl else None
    if inflight and inflight.exists():
        pid = inflight.read_text().strip()
        if pid:
            with jsonl.open("a") as fh:
                fh.write(json.dumps({"part": pid, "engine": args.engine,
                                     "angle": args.angle, "error": "ProcessDied",
                                     "detail": "killed mid-render; not retried"}) + "\n")
            print(f"recorded {pid} as ProcessDied and skipping it", flush=True)
            ids = [i for i in ids if i != pid]
        inflight.unlink()

    rows = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for n, pid in enumerate(ids, 1):
            t0 = time.time()
            if inflight:
                inflight.write_text(pid)
            try:
                r = run_guarded(pid, args, tmp)
            except BaseException as exc:  # a part must not end the run
                r = {"part": pid, "engine": args.engine, "angle": args.angle,
                     "error": type(exc).__name__, "detail": str(exc)[:300],
                     "traceback": traceback.format_exc()[-1200:]}
            r["secs"] = round(time.time() - t0, 1)
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
            if jsonl:
                with jsonl.open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
            for f in tmp.glob(f"{pid}.*"):
                f.unlink(missing_ok=True)
            if inflight:
                inflight.unlink(missing_ok=True)
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=1))
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
