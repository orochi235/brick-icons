#!/usr/bin/env python3
"""Score stored drawings against the edges their part files declare.

    scripts/score-declared-edges.py --emit-list --source white-occt > edges.txt
    onto run ... -- .venv/bin/python scripts/score-declared-edges.py \
        --source white-occt --list edges.txt --jsonl out/edges/white-occt.jsonl
    scripts/score-declared-edges.py --ingest out/edges/white-occt.jsonl

Reads each SVG and the `.fit.json` beside it, so nothing is redrawn and a fleet
node needs no corpus.db -- only the drawings and the library. `--overlay DIR`
writes each drawing with its visible declared edges in red and its gaps boxed,
for looking before trusting a number.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import build, cli, db, edge_truth, hlr  # noqa: E402
from brick_icons.batch import Runner  # noqa: E402

FONT = "/System/Library/Fonts/Helvetica.ttc"


def config(part: str, source: str):
    return cli._config_from_args(cli.build_parser().parse_args(
        db.canonical_argv(part, source)))


def one(svg: Path, source: str, zoom: int, overlay: Path | None) -> dict:
    part = svg.stem
    fit_path = svg.with_suffix(".fit.json")
    if not fit_path.exists():
        raise FileNotFoundError(f"no camera beside the drawing: {fit_path}")
    fit = json.loads(fit_path.read_text())
    cfg = config(part, source)
    roots, pose = hlr.default_roots(cfg.ldraw_dir), cli.part_pose(cfg, part)
    got = edge_truth.score_drawing(part, svg, fit, roots, cfg.line_width,
                                   pose=pose, zoom=zoom)
    if overlay:
        draw_overlay(part, source, svg, fit, roots, pose, zoom, got, overlay)
    # Runner stamps the key only onto a failure's row; a success names its part
    # here or not at all.
    return {"part": part, "source": source, **got}


def attach_parts(conn, rows: list[dict]) -> list[dict]:
    """Rows written before `one` named its part carry only the drawing's sha.
    Every part whose stored drawing in that slot has those bytes gets the
    score -- identical bytes are identical geometry, as with a moved part and
    the part it redirects to. A sha no stored drawing has any more is dropped."""
    owners: dict[tuple, list[str]] = {}
    for src in {r.get("source") for r in rows if not r.get("part")}:
        for pid, sha in conn.execute(
                "SELECT part_id, sha256 FROM renders WHERE source = ?", (src,)):
            owners.setdefault((src, sha), []).append(pid)
    out = []
    for r in rows:
        if r.get("part"):
            out.append(r)
        else:
            out += [{**r, "part": pid}
                    for pid in owners.get((r.get("source"), r.get("sha256")), [])]
    return out


def draw_overlay(part, source, svg, fit, roots, pose, zoom, got, out_dir):
    with tempfile.TemporaryDirectory() as td:
        png = Path(td) / "d.png"
        subprocess.run(["resvg", "--zoom", str(zoom), str(svg), str(png)],
                       check=True, capture_output=True)
        base = Image.alpha_composite(
            Image.new("RGBA", Image.open(png).size, "white"),
            Image.open(png).convert("RGBA"))
    ink = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)
    for x1, y1, x2, y2, _ in edge_truth.visible_edges(
            edge_truth.load(part, roots, pose), fit, zoom):
        d.line([(x1 * zoom, y1 * zoom), (x2 * zoom, y2 * zoom)],
               fill=(230, 30, 30, 170), width=max(1, zoom // 2))
    for g in got["gaps"]:
        pad = 2 * zoom
        d.rectangle([g["x"][0] * zoom - pad, g["y"][0] * zoom - pad,
                     g["x"][1] * zoom + pad, g["y"][1] * zoom + pad],
                    outline=(200, 0, 200, 255), width=zoom)
    art = Image.alpha_composite(base, ink)
    font = ImageFont.truetype(FONT, 14 * max(1, zoom // 2))
    title = (f"{part} {source} -- red: visible declared edges, magenta box: "
             f"gap ({got['missing_comps']} gaps, {got['missing_len']:.0f} of "
             f"{got['declared_len']:.0f} px uncovered)")
    head = 30 * max(1, zoom // 2)
    sheet = Image.new("RGB", (art.width, art.height + head), "white")
    ImageDraw.Draw(sheet).text((8, 6), title, fill="black", font=font)
    sheet.paste(art.convert("RGB"), (0, head))
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(out_dir / f"{part}-{source}-edges.png")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("svgs", nargs="*", type=Path)
    ap.add_argument("--source", help="the slot the drawings were filed under")
    ap.add_argument("--list", help="file of SVG paths, one per line")
    ap.add_argument("--jsonl", help="append one row per drawing here")
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--timeout", type=float, default=0)
    ap.add_argument("--zoom", type=int, default=4, help="raster px per canvas px")
    ap.add_argument("--overlay", type=Path, help="write a labeled overlay per drawing")
    ap.add_argument("--emit-list", action="store_true",
                    help="print the stored SVG paths for --source and exit")
    ap.add_argument("--ingest", help="write a finished JSONL into corpus.db and exit")
    args = ap.parse_args()

    if args.ingest:
        rows = [json.loads(ln) for ln in Path(args.ingest).read_text().splitlines()
                if ln.strip()]
        conn = db.connect()
        print(f"filed {db.record_edge_scores(conn, attach_parts(conn, rows))} "
              f"from {len(rows)} rows")
        return 0
    if not args.source:
        ap.error("--source is required")
    if args.emit_list:
        conn = db.connect()
        for (path,) in conn.execute(
                "SELECT path FROM renders WHERE source = ? AND path LIKE '%.svg' "
                "ORDER BY part_id", (args.source,)):
            print(path)
        return 0

    svgs = list(args.svgs)
    if args.list:
        svgs += [Path(s) for ln in Path(args.list).read_text().splitlines()
                 if (s := ln.strip())]
    if not svgs:
        ap.error("name at least one SVG, or pass --list")
    by_part = {p.stem: p for p in svgs}

    extra = {"source": args.source, "build": build()}
    runner = Runner(args.jsonl, timeout=args.timeout, key="part",
                    extra=extra) if args.jsonl else None
    ids = list(by_part)
    total = len(ids)
    if runner and args.skip_done:
        ids = runner.remaining(ids)
    # onto reads these off the item's own pipe: without them a batch is a bar
    # that moves once, when the batch ends.
    print(f"onto: plan {total - len(ids)}/{total}", flush=True)
    for n, pid in enumerate(ids, 1):
        print(f"onto: progress {total - len(ids) + n - 1}/{total}", flush=True)
        def work(part):
            return one(by_part[part], args.source, args.zoom, args.overlay)
        if runner:
            r = runner.run(pid, work)
        else:
            r = {"part": pid, **extra, **work(pid)}
        if "error" in r:
            print(f"{n}/{len(ids)} {pid}: FAILED {r['error']}: "
                  f"{str(r.get('detail', '')).splitlines()[0][:120]}", flush=True)
        else:
            print(f"{n}/{len(ids)} {pid}: {r['missing_comps']} gaps, "
                  f"{r['missing_len']:6.1f} of {r['declared_len']:7.1f} px "
                  f"uncovered", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
