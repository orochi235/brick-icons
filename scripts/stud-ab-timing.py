#!/usr/bin/env python3
"""What stud instancing costs or saves, per part, on one machine.

    .venv/bin/python scripts/stud-ab-timing.py --engine occt --reps 2 \
        --jsonl out/stud-ab/occt.jsonl 3811 3867 41539 3036 3958 3001

Draws each part with `--stud-instancing off` and `all` in one process,
interleaved A B B A per rep, after one untimed draw that fills the mesh
cache. A sequential A/B measures the node's load, not the code; interleaving
part by part lands any drift on both sides alike. Prints one line per part --
median seconds each way, the ratio, the stud counts -- and appends the same
as a JSON row to --jsonl.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, timing  # noqa: E402


def draw(part, mode, a, out):
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", a.shade, "--engine", a.engine, "--angle", "iso",
            "--stud-instancing", mode, "--root", str(ROOT), "--out", str(out)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    timing.reset()
    t0 = time.perf_counter()
    cli.process_one(cfg, part, out)
    return time.perf_counter() - t0, timing.counts()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", help="file of part[<TAB>label] lines")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--shade", default="flat3")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--jsonl")
    a = ap.parse_args(argv)
    parts = list(a.parts)
    if a.list:
        parts += [ln.split("\t")[0].strip()
                  for ln in Path(a.list).read_text().splitlines()
                  if ln.strip() and not ln.startswith("#")]
    if not parts:
        ap.error("name at least one part, or pass --list")
    if a.reps < 1:
        ap.error("--reps must be at least 1")
    sink = Path(a.jsonl) if a.jsonl else None
    if sink:
        sink.parent.mkdir(parents=True, exist_ok=True)
    print(f"{'part':>12} {'off s':>8} {'all s':>8} {'all/off':>8}  studs",
          flush=True)
    for part in parts:
        secs, counts = {"off": [], "all": []}, {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            try:
                draw(part, "off", a, out)               # warm-up: mesh cache
                for _ in range(a.reps):
                    for mode in ("off", "all", "all", "off"):
                        s, c = draw(part, mode, a, out)
                        secs[mode].append(round(s, 3))
                        if mode == "all":
                            counts = {k: v for k, v in c.items()
                                      if k.startswith("studs_")}
            except Exception as e:
                print(f"{part:>12} FAILED {type(e).__name__}: {e}", flush=True)
                continue
        off = statistics.median(secs["off"])
        on = statistics.median(secs["all"])
        ratio = round(on / off, 3) if off else None
        row = {"part": part, "engine": a.engine, "off": off, "all": on,
               "ratio": ratio, "counts": counts, "runs": secs}
        shown = f"{'n/a':>8}" if ratio is None else f"{ratio:8.3f}"
        studs = " ".join(f"{k[6:]}={v}" for k, v in sorted(counts.items()))
        print(f"{part:>12} {off:8.2f} {on:8.2f} {shown}  {studs}", flush=True)
        if sink:
            with sink.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
