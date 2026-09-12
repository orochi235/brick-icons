#!/usr/bin/env python
"""Which class of drawn op puts ink where, for one part under `naive`.

Renders a part once per suppressed class and diffs each against the baseline,
so a line nobody can account for gets attributed to the rule that emitted it
rather than guessed at. Classes:

  cyl-sil-far   a cylinder/cone silhouette generator at theta+pi
  cyl-sil       both generators
  cond          type-5 conditional lines that passed the same-side test
  rim           wall base/top rim arcs

Usage: probe-drawn-classes.py 24434 [--out DIR]
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import hlr, primitives  # noqa: E402

CLASSES = ("cyl-sil-far", "cyl-sil", "cond", "rim", "fitarc", "type2")


def patch(name: str):
    """Install the suppression `name` asks for; returns an undo callable."""
    undo = []

    def wrap_wall(cls, keep_near_only: bool, drop_sil: bool, drop_rim: bool):
        original = cls.drawn_with_depth

        def patched(self, proj, skip_rims=None):
            pairs = original(self, proj, skip_rims=skip_rims)
            out = []
            sil_seen = 0
            for op, dfn in pairs:
                is_sil = op[-1] == "sil"
                if is_sil:
                    sil_seen += 1
                    if drop_sil:
                        continue
                    if keep_near_only and sil_seen > 1:
                        continue
                elif drop_rim and op[0] == "arc":
                    continue
                out.append((op, dfn))
            return out

        cls.drawn_with_depth = patched
        undo.append(lambda: setattr(cls, "drawn_with_depth", original))

    if name in ("cyl-sil-far", "cyl-sil", "rim"):
        for cls in (primitives.Cylinder, primitives.Cone):
            wrap_wall(cls, keep_near_only=(name == "cyl-sil-far"),
                      drop_sil=(name == "cyl-sil"), drop_rim=(name == "rim"))
    elif name in ("fitarc", "type2"):
        from brick_icons import arcfit
        original = arcfit.fit_edge_arcs

        def patched(twos, fives):
            arcs, kept = original(twos, fives)
            if name == "fitarc":
                return [], list(kept) + [a for a in ()]
            return arcs, []

        arcfit.fit_edge_arcs = patched
        undo.append(lambda: setattr(arcfit, "fit_edge_arcs", original))
    elif name == "cond":
        original = hlr.same_side
        hlr.same_side = lambda *a, **k: False
        undo.append(lambda: setattr(hlr, "same_side", original))
    else:
        raise ValueError(f"unknown class {name!r}")

    def restore():
        for fn in undo:
            fn()
    return restore


def render(part: str, out: Path) -> Path:
    from brick_icons import cli
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", "white", "--angle", "iso", "--engine", "naive",
            "--line-width", "2", "--silhouette-width", "2",
            "--out", str(out)]
    args = cli.build_parser().parse_args(argv)
    cli.process_one(cli._config_from_args(args), part, out)
    return out / f"{part}.svg"


def png(svg: Path, width: int) -> Path:
    dst = svg.with_suffix(".png")
    subprocess.run(["resvg", "--background", "white", "--width", str(width),
                    str(svg), str(dst)], check=True)
    return dst


def ink(path: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("L"), dtype=np.int16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--out", default="out/probe-classes")
    ap.add_argument("--width", type=int, default=900)
    args = ap.parse_args()

    out = Path(args.out) / args.part
    out.mkdir(parents=True, exist_ok=True)

    base = png(render(args.part, out / "baseline"), args.width)
    base_ink = ink(base)
    total = int((base_ink < 128).sum())
    print(f"baseline: {total} ink px  -> {base}")

    for i, name in enumerate(CLASSES, 1):
        restore = patch(name)
        try:
            shot = png(render(args.part, out / name), args.width)
        finally:
            restore()
        cut = ink(shot)
        gone = int(((base_ink < 128) & (cut >= 128)).sum())
        added = int(((base_ink >= 128) & (cut < 128)).sum())
        print(f"{i}/{len(CLASSES)} {name:<12} removes {gone:>6} px, "
              f"adds {added:>6} px  -> {shot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
