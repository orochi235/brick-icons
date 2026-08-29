#!/usr/bin/env python3
"""Diff a fresh engine run against the frozen goldens.

    python scripts/freeze-goldens.py --out /tmp/new
    python scripts/compare-goldens.py /tmp/new --out report.md

Hashes are deliberately not checked here: a different engine misses every one
of them by construction, which is what `tests/test_goldens.py` is for. This
compares the two things that should survive a swap — the rasterized drawing
and the structural summary.

Read the arc/line split as intent, not drift. OCCT emits `Geom_Circle` edges
where the naive path refits a polyline, so on round parts `A` rising while
`L` falls is the swap working. A round part whose `A` count does NOT move is
the suspicious one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FROZEN = ROOT / "tests" / "goldens"


def raster_delta(a: Path, b: Path):
    """(rmse, max_abs, note) over 0-255 RGB composited on white."""
    if not a.exists() or not b.exists():
        return None, None, "missing raster"
    ia, ib = Image.open(a).convert("RGBA"), Image.open(b).convert("RGBA")
    if ia.size != ib.size:
        return None, None, f"size {ia.size} vs {ib.size}"
    fa, fb = (_on_white(ia), _on_white(ib))
    diff = np.abs(fa - fb)
    return float(np.sqrt((diff ** 2).mean())), float(diff.max()), None


def _on_white(im: Image.Image) -> np.ndarray:
    arr = np.asarray(im).astype(np.float64)
    rgb, alpha = arr[..., :3], arr[..., 3:4] / 255.0
    return rgb * alpha + 255.0 * (1.0 - alpha)


def summary_delta(old: dict, new: dict) -> list[str]:
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if key == "bbox" and a and b:
            shift = max(abs(x - y) for x, y in zip(a, b))
            out.append(f"bbox shifts {shift:.2f}")
        elif isinstance(a, dict) and isinstance(b, dict):
            moved = {k: (a.get(k, 0), b.get(k, 0))
                     for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
            out.append(f"{key} " + ", ".join(
                f"{k} {x}->{y}" for k, (x, y) in moved.items()))
        else:
            out.append(f"{key} {a!r}->{b!r}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fresh", help="directory written by freeze-goldens.py --out")
    ap.add_argument("--frozen", default=str(FROZEN))
    ap.add_argument("--out", help="write a markdown report here")
    ap.add_argument("--rmse-tol", type=float, default=0.0,
                    help="raster RMSE at or below this is quiet")
    ap.add_argument("--bbox-tol", type=float, default=0.0)
    args = ap.parse_args(argv)

    frozen = Path(args.frozen) / "render"
    fresh = Path(args.fresh) / "render"
    cases = sorted(p.stem for p in frozen.glob("*.json"))
    if not cases:
        print(f"no goldens under {frozen}", file=sys.stderr)
        return 2

    rows, noisy = [], 0
    for i, cid in enumerate(cases, 1):
        old = json.loads((frozen / f"{cid}.json").read_text())
        new_path = fresh / f"{cid}.json"
        if not new_path.exists():
            rows.append((cid, None, None, ["absent from the fresh run"]))
            noisy += 1
            print(f"{i}/{len(cases)} {cid}  MISSING", flush=True)
            continue
        new = json.loads(new_path.read_text())
        rmse, peak, note = raster_delta(frozen / f"{cid}.png", fresh / f"{cid}.png")
        notes = summary_delta(old, new)
        if note:
            notes.insert(0, note)
        over = (rmse is None or rmse > args.rmse_tol
                or any(not n.startswith("bbox shifts") for n in notes)
                or any(n.startswith("bbox shifts")
                       and float(n.split()[-1]) > args.bbox_tol for n in notes))
        rows.append((cid, rmse, peak, notes))
        noisy += bool(over)
        head = "----" if rmse is None else f"rmse {rmse:6.3f} peak {peak:5.1f}"
        print(f"{i}/{len(cases)} {cid}  {head}  "
              f"{'; '.join(notes) if notes else 'identical'}", flush=True)

    print(f"\n{len(cases)} cases, {noisy} over tolerance")
    if args.out:
        lines = ["# Golden comparison", "",
                 f"{len(cases)} cases, {noisy} over tolerance "
                 f"(rmse tol {args.rmse_tol}, bbox tol {args.bbox_tol})", "",
                 "| case | rmse | peak | differences |", "|---|---|---|---|"]
        for cid, rmse, peak, notes in rows:
            lines.append(f"| `{cid}` | {'—' if rmse is None else f'{rmse:.3f}'} "
                         f"| {'—' if peak is None else f'{peak:.1f}'} "
                         f"| {'; '.join(notes) if notes else 'identical'} |")
        Path(args.out).write_text("\n".join(lines) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
