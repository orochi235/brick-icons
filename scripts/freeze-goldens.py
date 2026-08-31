#!/usr/bin/env python3
"""Freeze the naive engine's output as the conformance baseline.

Run before any engine work lands, and again on the new engine to compare:

    python scripts/freeze-goldens.py                  # write tests/goldens/
    python scripts/freeze-goldens.py --out /tmp/new   # a run to compare

Each case yields three artifacts. The SHA in `hashes.txt` is an exact drift
lock on the naive engine and nothing else — a different engine fails it by
construction. The `.json` summary and the `.png` raster are the comparable
pair `compare-goldens.py` actually diffs.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import goldens  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "goldens" / "manifest.toml"


def load_cases(manifest: Path):
    cfg = tomllib.loads(manifest.read_text())
    lists = cfg["parts"]
    cases = []
    for combo, spec in sorted(cfg["combo"].items()):
        names = spec["parts"]
        parts = lists[names] if isinstance(names, str) else names
        for part in parts:
            cases.append({"id": f"{combo}__{part}", "combo": combo,
                          "part": part, "args": spec["args"]})
    return cases, cfg.get("raster", {}).get("width", 512)


def read_hashes(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        sha, _, cid = line.partition("  ")
        if cid.strip():
            out[cid.strip()] = sha
    return out


def read_decal_hashes(path: Path) -> dict[str, tuple[str, int]]:
    """`sha  part  n` — the count is part of the golden, not a comment: a part
    dropping from 2 decals to 1 is drift even when the surviving SVG matches."""
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 3:
            out[fields[1]] = (fields[0], int(fields[2]))
    return out


def run_case(case, work: Path) -> tuple[str | None, str | None]:
    """Render one case. Returns (svg_text, error)."""
    out = work / case["id"]
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", case["part"],
         *case["args"], "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if proc.returncode != 0 or not svgs:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, (tail[-1] if tail else f"exit {proc.returncode}, no svg")
    return svgs[0].read_text(), None


def rasterize(svg: Path, png: Path, width: int) -> str | None:
    if not shutil.which("resvg"):
        return "resvg not on PATH"
    proc = subprocess.run(["resvg", "--width", str(width), str(svg), str(png)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return (proc.stderr.strip().splitlines() or ["resvg failed"])[-1]
    return None


def freeze_extraction(out: Path, corpus: Path, only: str | None) -> int:
    """The `decal` seam: `hlr.part_geometry`, no view pipeline.

    One hash per part covering all of its decals, not one per SVG — a corpus
    this size yields ~12k files, and per-part granularity localizes drift just
    as well at a twentieth of the rows.
    """
    parts = [ln.split("#")[0].strip()
             for ln in corpus.read_text().splitlines()]
    parts = [p for p in parts if p]
    if only:
        wanted = set(only.split(","))
        parts = [p for p in parts if p in wanted]
        if not parts:
            print(f"no corpus part matches --only {only}")
            return 2
    work = out / ".work-decal"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)

    # One invocation, not 600: interpreter startup dominates a seam that costs
    # 0.04s of actual work per part. The CLI prints its own [i/N] progress.
    # The CLI gets the FILTERED list, not the corpus: filtering only the rows
    # we hash still extracts all 393 parts, which is the whole cost.
    listing = work / "parts.txt"
    listing.write_text("".join(f"{p}\n" for p in parts))
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", "decal",
         "--list", str(listing), "--out", str(work)],
        text=True, cwd=ROOT)

    svgs = sorted(work.glob("*.decal*.svg"))
    by_part: dict[str, list[Path]] = {}
    for svg in svgs:
        by_part.setdefault(svg.name.split(".decal")[0], []).append(svg)

    rows = []
    for part in parts:
        got = by_part.get(part, [])
        blob = "".join(p.read_text() for p in got)
        rows.append((part, goldens.sha256(blob), len(got)))
    shutil.rmtree(work, ignore_errors=True)

    # Merge, never overwrite — same reason as the render seam: an --only run
    # must not drop the parts it did not rebuild.
    merged = read_decal_hashes(out / "decal-hashes.txt")
    merged.update({p: (h, n) for p, h, n in rows})
    (out / "decal-hashes.txt").write_text(
        "".join(f"{h}  {p}  {n}\n" for p, (h, n) in sorted(merged.items())))
    empty = sum(1 for _, _, n in rows if not n)
    # The decal CLI exits 1 whenever any part yields nothing, which is a normal
    # census result rather than a failure — plenty of printed parts carry no
    # extractable decoration. Only a crash is worth propagating.
    print(f"\n{len(parts)} parts, {len(svgs)} svgs, {empty} carrying no decal")
    return 0 if proc.returncode in (0, 1) else proc.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "tests" / "goldens"))
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--only",
                    help="render seam: substring filter on the case id. "
                         "extraction seam: comma-separated exact part ids")
    ap.add_argument("--seam", choices=["render", "extraction"],
                    default="render")
    args = ap.parse_args(argv)

    if args.seam == "extraction":
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        return freeze_extraction(out, ROOT / "tests" / "goldens"
                                 / "decal-corpus.txt", args.only)

    cases, width = load_cases(Path(args.manifest))
    if args.only:
        cases = [c for c in cases if args.only in c["id"]]
    out = Path(args.out)
    render_dir = out / "render"
    render_dir.mkdir(parents=True, exist_ok=True)
    work = out / ".work"
    work.mkdir(parents=True, exist_ok=True)

    hashes, failures = {}, 0
    for i, case in enumerate(cases, 1):
        t0 = time.time()
        svg, err = run_case(case, work)
        summary = {"error": err} if err else goldens.summarize_svg(svg)
        if svg is not None:
            svg_path = render_dir / f"{case['id']}.svg"
            svg_path.write_text(svg)
            hashes[case["id"]] = goldens.sha256(svg)
            rerr = rasterize(svg_path, render_dir / f"{case['id']}.png", width)
            if rerr:
                summary["raster_error"] = rerr
            svg_path.unlink()
        (render_dir / f"{case['id']}.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n")
        note = f"ERROR {err}" if err else (
            f"{summary['paths']} paths, {summary['commands'].get('A', 0)} arcs")
        failures += bool(err)
        print(f"{i}/{len(cases)} {case['id']}  {time.time() - t0:.1f}s  {note}",
              flush=True)

    # Merge, never overwrite: a --only run must not drop the cases it did not
    # rebuild, and a filtered re-freeze is the common way to fix one case.
    merged = read_hashes(out / "hashes.txt")
    merged.update(hashes)
    (out / "hashes.txt").write_text(
        "".join(f"{h}  {cid}\n" for cid, h in sorted(merged.items())))
    shutil.rmtree(work, ignore_errors=True)
    print(f"\n{len(cases)} cases, {len(hashes)} hashed, {failures} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
