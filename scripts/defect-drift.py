#!/usr/bin/env python3
"""Which open defects' drawings have moved since they were filed.

    .venv/bin/python scripts/defect-drift.py --before 44aeaf1 --workers 6
    .venv/bin/python scripts/defect-drift.py --before 44aeaf1 --engine decal \
        --out out/sheets/drift.jsonl

Every render in the corpus is behind at least one drawing commit, so an open
defect filed in September was filed against a picture nobody draws any more.
This says which ones could possibly have been fixed since: it draws the part
at `--before` and at HEAD and component-counts the difference.

**`unchanged` does NOT mean the defect still stands.** That was this script's
first premise and it is wrong: on 2026-09-16 nine `mirrored` decal defects came
back pixel-identical between 44aeaf1 and HEAD and not one of them reproduced.
A defect is filed against the CORPUS render the lab was showing, which is older
than any build you can name here and is overwritten the next time the slot is
filled -- so there is no build to diff against that answers "is this still
true". Only `defect-sheet.py`, drawing the part beside the browser reference,
answers that.

What this does answer is the narrower question it measures: did some engine
change between two builds move this part's drawing. That is worth knowing
before and after an engine commit, and it is not a defect triage filter.

Components, not pixels: antialias fringe scatters into hundreds of one- and
two-pixel specks whatever changed, so a pixel count says "different" for every
part. `MIN_PX` is the floor a component has to clear to count as a real one.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tomllib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import db  # noqa: E402

DEFECTS = ROOT / "tests" / "goldens" / "defects.toml"

#: Pixels a diff component must reach to be a change rather than a fringe.
MIN_PX = 12
WIDTH = 512

#: A defect names an engine; the wall draws it in a slot. This is which slot
#: stands for which engine when the record does not say.
SLOT = {"occt": "occt", "naive": "naive", "decal": "decal",
        "reference": "reference"}


def _draw(part: str, source: str, tree: Path, into: Path) -> np.ndarray | None:
    into.mkdir(parents=True, exist_ok=True)
    for old in into.glob("*"):
        old.unlink()
    argv = list(db._CANONICAL[source])
    if "--format" not in argv:
        argv += ["--format", "svg"]
    env = {**os.environ, "PYTHONPATH": str(tree)}
    r = subprocess.run([str(ROOT / ".venv/bin/python"), "-m", "brick_icons.cli",
                        part, *argv, "--out", str(into)],
                       capture_output=True, text=True, cwd=tree, env=env)
    if r.returncode != 0:
        return None
    svgs = sorted(into.glob(f"{part}.*svg"))
    if not svgs:
        return None
    png = svgs[0].with_suffix(".drift.png")
    subprocess.run(["resvg", "-w", str(WIDTH), str(svgs[0]), str(png)],
                   capture_output=True)
    if not png.exists():
        return None
    im = Image.open(png).convert("RGBA")
    flat = Image.new("RGBA", im.size, "white")
    flat.alpha_composite(im)
    return np.asarray(flat.convert("RGB"), dtype=np.int16)


def one(job) -> dict:
    part, source, before_tree, tmp = job
    out = {"part": part, "source": source}
    a = _draw(part, source, Path(before_tree), Path(tmp) / "before")
    b = _draw(part, source, ROOT, Path(tmp) / "after")
    if a is None or b is None:
        out["drift"] = "render failed"
        return out
    if a.shape != b.shape:
        out["drift"] = "size changed"
        out["comps"] = 999
        return out
    mask = np.abs(a - b).max(axis=2) > 24
    lab, n = ndimage.label(mask)
    sizes = ndimage.sum(mask, lab, range(1, n + 1)) if n else np.array([])
    big = int((sizes >= MIN_PX).sum())
    out["comps"] = big
    out["px"] = int(mask.sum())
    out["drift"] = "moved" if big else "unchanged"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--before", required=True, help="revision to draw against")
    ap.add_argument("--engine", help="only defects filed against this engine")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--tmp", type=Path, default=Path("/tmp/defect-drift"))
    a = ap.parse_args(argv)

    wt = a.tmp / f"wt-{a.before}"
    if not wt.is_dir():
        subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach",
                        str(wt), a.before], check=True, capture_output=True)
    if not (wt / "vendor").exists():
        (wt / "vendor").symlink_to(ROOT / "vendor")

    rows = [r for r in tomllib.load(DEFECTS.open("rb"))["defect"]
            if r.get("status") == "open"]
    if a.engine:
        rows = [r for r in rows if a.engine in r.get("engines", [])]
    jobs, seen = [], set()
    for r in rows:
        source = SLOT.get(r.get("engines", ["occt"])[0], "occt")
        if source == "reference" or (r["part"], source) in seen:
            continue
        seen.add((r["part"], source))
        jobs.append((r["part"], source, str(wt),
                     str(a.tmp / f"{source}-{r['part']}")))

    print(f"{len(jobs)} parts, {a.before} vs HEAD, {a.workers} workers",
          flush=True)
    results = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, res in enumerate(ex.map(one, jobs), 1):
            results.append(res)
            print(f"{i:4d}/{len(jobs)} {res['part']:14s} {res['source']:8s} "
                  f"{res['drift']:14s} {res.get('comps', '-')}", flush=True)

    moved = [r for r in results if r["drift"] == "moved"]
    print(f"\nmoved {len(moved)}   unchanged "
          f"{sum(1 for r in results if r['drift'] == 'unchanged')}   "
          f"failed {sum(1 for r in results if r['drift'] == 'render failed')}")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text("\n".join(json.dumps(r) for r in results) + "\n")
        print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
