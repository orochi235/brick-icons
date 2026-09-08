#!/usr/bin/env python3
"""Render each part on occt with and without `_snap_rim_crossings` pass 1.

    .venv/bin/python scripts/snap-render-ab.py --list out/snap-affected.txt \
        --out out/snap-render-ab --results out/snap-render-ab.json

`scripts/measure-snap-gaps.py` says the pass WOULD move an endpoint; it cannot
say the move is right. This draws both sides and component-counts the diff, so
a chunky change can be looked at and a fringe-only one ignored -- antialias
scatters into hundreds of tiny components and a real change is a handful of
big ones.

The pass is spliced in ahead of `arcfit.fit_silhouette_arcs`, which is where
the naive branch runs it. Nothing in the tree is edited.

`--results` is JSON Lines, one row appended and flushed as each part finishes,
because a run over the whole affected list takes hours: writing at the end once
cost 9h38m of work to a timeout that left an empty file. Re-running with the
same `--results` resumes -- parts that already have a row are skipped, and a
part whose row records an error is retried after every part that has not been
tried at all.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import arcfit, cli, hlr, occt  # noqa: E402

_seen: dict = {}
_occt_vs = occt.visible_segments
_fit = arcfit.fit_silhouette_arcs


def _spy(*a, **kw):
    res = _occt_vs(*a, **kw)
    _seen["s"] = res.s
    return res


def _snap_then_fit(segs, *a, **kw):
    # vertex_tol is op units, and occt works in projected LDU (cf. dedupe's eps)
    segs, _ = hlr._snap_rim_crossings(segs, vertex_tol=0.25 / (_seen.get("s") or 1.0))
    return _fit(segs, *a, **kw)


def render(part: str, out: Path, tag: str, snap: bool, width: int) -> Path:
    argv = [part, "--format", "svg", "--shading", "outline", "--shade-style",
            "flat3", "--angle", "iso", "--engine", "occt", "--out", str(out),
            "--width", str(width), "--height", str(width)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    occt.visible_segments = _spy
    if snap:
        arcfit.fit_silhouette_arcs = _snap_then_fit
    try:
        cli.process_one(cfg, part, out)
    finally:
        arcfit.fit_silhouette_arcs = _fit
        occt.visible_segments = _occt_vs
    dst = out / f"{part}.{tag}.svg"
    (out / f"{part}.svg").replace(dst)
    return dst


def raster(svg: Path, zoom: float) -> np.ndarray:
    png = svg.with_suffix(".png")
    subprocess.run(["resvg", "--zoom", str(zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    return np.asarray(Image.open(png).convert("RGB")).astype(int)


def read_rows(path: Path | None) -> dict[str, dict]:
    """Rows a previous run already wrote, by part. Last row per part wins, so
    a retried failure supersedes the row that recorded it."""
    if not path or not path.is_file():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            row = json.loads(line)
            out[row["part"]] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=Path, required=True)
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--out", type=Path, default=Path("out/snap-render-ab"))
    ap.add_argument("--results", type=Path)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--zoom", type=float, default=2.0)
    ap.add_argument("--chunk", type=int, default=12,
                    help="px; a diff component this size or bigger is real")
    ap.add_argument("--restart", action="store_true",
                    help="ignore any rows already in --results and redo them")
    args = ap.parse_args()

    parts = list(args.parts) + [ln.split("#")[0].strip() for ln
                                in args.list.read_text().splitlines()]
    parts = [p for p in parts if p]
    args.out.mkdir(parents=True, exist_ok=True)

    done = {} if args.restart else read_rows(args.results)
    # Never-tried outranks errored: a part nobody has measured is worth more
    # than a retry of one that blew up, and a run that dies partway should
    # still have covered every fresh part.
    fresh = [p for p in parts if p not in done]
    retry = [p for p in parts if p in done and done[p].get("error")]
    queue = fresh + retry
    if done:
        print(f"{len(done)} rows already in {args.results}: "
              f"{len(fresh)} not tried, {len(retry)} to retry, "
              f"{len(parts) - len(queue)} done", flush=True)

    sink = args.results.open("w" if args.restart else "a") if args.results else None
    if sink and args.restart:
        done = {}

    def keep(row: dict) -> None:
        done[row["part"]] = row
        if sink:
            sink.write(json.dumps(row) + "\n")
            sink.flush()          # a run this long must survive being killed

    failed = 0
    for i, part in enumerate(queue, 1):
        t = time.perf_counter()
        try:
            a = raster(render(part, args.out, "off", False, args.width), args.zoom)
            b = raster(render(part, args.out, "on", True, args.width), args.zoom)
        except BaseException as e:
            failed += 1
            keep({"part": part, "error": f"{type(e).__name__}: {e}"})
            print(f"{i}/{len(queue)} {part:<14} FAILED {type(e).__name__}: {e}",
                  flush=True)
            if isinstance(e, KeyboardInterrupt):
                raise
            continue
        mask = np.abs(a - b).sum(2) > 24
        lab, n = ndimage.label(mask, np.ones((3, 3)))
        sizes = np.bincount(lab.ravel())[1:] if n else np.zeros(0, int)
        chunky = int((sizes >= args.chunk).sum())
        keep({"part": part, "diff_px": int(mask.sum()), "comps": int(n),
              "chunky": chunky, "largest": int(sizes.max()) if n else 0})
        print(f"{i}/{len(queue)} {part:<14} diff {int(mask.sum()):6d}px  "
              f"comps {n:4d}  chunky {chunky:3d}  largest "
              f"{done[part]['largest']:5d}  {time.perf_counter() - t:5.1f}s",
              flush=True)
    if sink:
        sink.close()

    rows = [r for r in done.values() if not r.get("error")]
    moved = [r for r in rows if r["chunky"]]
    print()
    print(f"{len(rows)} parts rendered, {failed} failed this run, "
          f"{sum(1 for r in done.values() if r.get('error'))} failing in total")
    print(f"  parts with a chunky (>= {args.chunk}px) change: {len(moved)}")
    if moved:
        big = sorted(moved, key=lambda r: -r["largest"])[:15]
        print("  worst by largest component:")
        for r in big:
            print(f"    {r['part']:<14} chunky {r['chunky']:3d}  "
                  f"largest {r['largest']:5d}px")
    if args.results:
        print(f"  {len(done)} rows in {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
