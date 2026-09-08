#!/usr/bin/env python3
"""How many parts the coplanar paint-order fix (`a38e5a8`, narrowed by
`83ba303`) actually redraws, measured by rendering each part twice in ONE
process with the fix armed and disarmed.

    .venv/bin/python scripts/coplanar-affected.py --list out/stickers.txt \
        --out-dir out/coplanar --save-dir out/coplanar/png

**A census cannot answer this.** `compare-silhouette-truth` scores
`alpha > 128`, and paint order changes which color wins *inside* the
silhouette, never whether a pixel is opaque -- so every census number comes
out identical while the artwork appears and disappears.

The fix is a gate inside `shade.order_faces`, not a constant, so disarming it
means blinding the thing the gate reads: set every face's `color` to one value
IN PLACE (identity preserved, so `own_occ`'s id() keys still resolve), call the
real `order_faces`, restore. Every coplanar pair then takes the `continue`,
which is exactly the pre-`a38e5a8` path. Both sides therefore run HEAD's code;
nothing depends on which tree the editable install resolves to.

Rasterize and diff -- a differing SVG is not a moved drawing here, the element
order changes on its own -- and composite onto white first, or a transparent
ground reads as all-black and every part scores a full-frame change.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, shade  # noqa: E402
from brick_icons.batch import Runner  # noqa: E402

_REAL = shade.order_faces
_MISSING = object()
BLIND = 16          # any single value: what matters is that all faces share it


def _disarmed(faces, proj=None, eps=1e-6, own_occ=None):
    saved = [f.get("color", _MISSING) for f in faces]
    for f in faces:
        f["color"] = BLIND
    try:
        return _REAL(faces, proj, eps, own_occ=own_occ)
    finally:
        for f, c in zip(faces, saved):
            if c is _MISSING:
                f.pop("color", None)
            else:
                f["color"] = c


def _armed(seen, calls):
    """Ships the real order, and notes whether the disarmed one would differ.

    That flag is the fast path: a part whose paint order the fix does not touch
    cannot draw differently, so the second render is skipped outright. The call
    count goes in the row beside it, because "the fix changes nothing here" and
    "this render never ordered any faces" are otherwise the same answer.

    Compare the SEQUENCE. An identical multiset is not an unmoved drawing --
    the stages below read the list in order, so the same faces in a different
    order still trace differently.
    """
    def call(faces, proj=None, eps=1e-6, own_occ=None):
        calls.append(True)
        out = _REAL(faces, proj, eps, own_occ=own_occ)
        keep = [(f, f.get("order")) for f in out]
        if [id(f) for f in _disarmed(faces, proj, eps, own_occ=own_occ)] \
                != [id(f) for f in out]:
            seen.append(True)
        for f, k in keep:                    # _disarmed restamped every order
            f["order"] = k
        return out
    return call


def _render(part: str, args, tmp: Path, order_fn) -> np.ndarray:
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", args.shade_style, "--angle", args.angle,
            "--engine", args.engine, "--render-px", str(args.render_px),
            "--out", str(tmp)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    shade.order_faces = order_fn
    try:
        cli.process_one(cfg, part, tmp)
    finally:
        shade.order_faces = _REAL
    svg, png = tmp / f"{part}.svg", tmp / f"{part}.png"
    subprocess.run(["resvg", "--zoom", str(args.zoom), str(svg), str(png)],
                   check=True, capture_output=True)
    rgba = np.array(Image.open(png).convert("RGBA")).astype(float)
    a = rgba[:, :, 3:4] / 255.0
    return (rgba[:, :, :3] * a + 255.0 * (1 - a)).round().astype(np.uint8)


def _keep(tmp: Path, part: str, side: str, save: Path | None) -> None:
    if save is None:
        return
    save.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "png"):
        src = tmp / f"{part}.{ext}"
        if src.is_file():
            src.replace(save / f"{part}.{side}.{ext}")


def one(part: str, args, tmp: Path) -> dict:
    t0 = time.perf_counter()
    seen: list[bool] = []
    calls: list[bool] = []
    save = Path(args.save_dir) if args.save_dir else None
    fix = _render(part, args, tmp, _armed(seen, calls))
    row = {"part": part, "order_differs": bool(seen), "orderings": len(calls)}
    if not seen:
        row.update(moves=False, changed_px=0, blobs=0,
                   secs=round(time.perf_counter() - t0, 2))
        return row
    _keep(tmp, part, "fix", save)
    ctl = _render(part, args, tmp, _disarmed)
    _keep(tmp, part, "ctl", save)

    d = np.abs(fix.astype(int) - ctl.astype(int)).max(axis=2) > args.tol
    lab, n = ndimage.label(d)
    blobs = 0
    if n:
        sizes = ndimage.sum(d, lab, range(1, n + 1))
        blobs = int((sizes >= args.floor).sum())
    row.update(moves=bool(d.any()), changed_px=int(d.sum()), blobs=blobs,
               px=int(d.size), secs=round(time.perf_counter() - t0, 2))
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", help="file with one part per line")
    ap.add_argument("--parts", dest="batch",
                    help="comma-separated ids, for onto --each; a "
                         "space-separated list arrives as one item")
    ap.add_argument("--out", help="jsonl to append to")
    ap.add_argument("--out-dir", help="write <first part>.jsonl here instead")
    ap.add_argument("--save-dir", help="keep both renders of every mover here")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--angle", default="iso")
    ap.add_argument("--shade-style", default="flat3")
    ap.add_argument("--render-px", type=int, default=512)
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--tol", type=int, default=8,
                    help="per-channel difference that counts as a changed px")
    ap.add_argument("--floor", type=int, default=8,
                    help="px: diff components smaller than this are AA fringe")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--isolate", action="store_true",
                    help="render in a forked child, so --timeout can stop it")
    ap.add_argument("--mem-gb", dest="mem_gb", type=float, default=8)
    args = ap.parse_args(argv)

    parts = list(args.parts)
    if args.batch:
        parts += [p.strip() for p in args.batch.split(",") if p.strip()]
    if args.list:
        parts += [s for ln in Path(args.list).read_text().splitlines()
                  if (s := ln.split("#")[0].strip())]
    if not parts:
        ap.error("name at least one part, or pass --list")
    if args.out_dir:
        # Named for the batch's first part, as census-batch.sh does it: a retry
        # that starts elsewhere must not append to another batch's file.
        out = Path(args.out_dir) / f"{parts[0]}.jsonl"
    elif args.out:
        out = Path(args.out)
    else:
        ap.error("need --out or --out-dir")

    out.parent.mkdir(parents=True, exist_ok=True)
    runner = Runner(out, timeout=args.timeout, key="part",
                    isolate=args.isolate, mem_gb=args.mem_gb)
    before = len(parts)
    parts = runner.remaining(parts)
    done = before - len(parts)
    print(f"resuming: {done} done, {len(parts)} left", flush=True)
    print(f"onto: plan {done}/{before}", flush=True)

    n, moved, bad = len(parts), 0, 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for i, part in enumerate(parts, 1):
            r = runner.run(part, lambda pid, tmp=tmp: one(pid, args, tmp))
            if "error" in r:
                bad += 1
                print(f"{i}/{n} {part} FAILED {r['error']} [{r.get('secs')}s]",
                      flush=True)
            elif r["moves"]:
                moved += 1
                print(f"{i}/{n} {part} MOVES {r['changed_px']}px "
                      f"{r['blobs']} blobs [{r['secs']}s]", flush=True)
            else:
                why = "order same" if not r["order_differs"] else "same pixels"
                print(f"{i}/{n} {part} {why} [{r['secs']}s]", flush=True)
            print(f"onto: progress {i}/{n}", flush=True)

    print(f"\nmoves {moved}/{n}; errors {bad}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
