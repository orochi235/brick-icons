#!/usr/bin/env python3
"""Render the frozen `outline` corpus under both engines and diff the summaries.

    python scripts/compare-engines.py --out /tmp/engines.json

`--engine naive` and `--engine occt` share the same CLI surface and both
produce SVGs `goldens.summarize_svg` can compare. This is not a golden diff
against `tests/goldens/` — it is naive-vs-occt, same case, same run, so a
different engine is expected to differ. The corpus itself must not move: only
`scripts/freeze-goldens.py` and `scripts/compare-goldens.py` touch
`tests/goldens/`.

Read the arc/line split as intent, not drift: on round parts `A` should rise
and `L` should fall as the kernel reports exact circles instead of refitted
polylines. A round part whose `A` count does not move is the suspicious one.
`bbox`, `viewBox` and the fill palette should hold roughly still.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import goldens  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "goldens" / "manifest.toml"


def load_outline_parts(manifest: Path) -> tuple[list[str], list[str]]:
    cfg = tomllib.loads(manifest.read_text())
    spec = cfg["combo"]["outline"]
    names = spec["parts"]
    parts = cfg["parts"][names] if isinstance(names, str) else names
    return parts, spec["args"]


def render(part: str, args: list[str], engine: str, work: Path) -> tuple[str | None, str | None]:
    out = work / f"{part}-{engine}"
    out.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "brick_icons.cli", part, *args,
         "--engine", engine, "--out", str(out)],
        capture_output=True, text=True, cwd=ROOT)
    svgs = sorted(out.glob("*.svg"))
    if proc.returncode != 0 or not svgs:
        tail = (proc.stderr or proc.stdout).strip().splitlines()
        return None, (tail[-1] if tail else f"exit {proc.returncode}, no svg")
    return svgs[0].read_text(), None


def line_for(part: str, naive: dict, occt: dict) -> str:
    if "error" in occt:
        return f"OCCT ERROR: {occt['error']}"
    if "error" in naive:
        return f"naive ERROR: {naive['error']}"

    nc, oc = naive["commands"], occt["commands"]
    a0, a1 = nc.get("A", 0), oc.get("A", 0)
    l0, l1 = nc.get("L", 0), oc.get("L", 0)
    bits = [f"A {a0}->{a1}", f"L {l0}->{l1}"]

    nb, ob = naive.get("bbox"), occt.get("bbox")
    if nb and ob:
        shift = max(abs(x - y) for x, y in zip(nb, ob))
        bits.append(f"bbox {'ok' if shift < 1.0 else f'SHIFT {shift:.2f}'}")
    elif nb != ob:
        bits.append(f"bbox {nb}->{ob}")

    if naive.get("viewBox") != occt.get("viewBox"):
        bits.append(f"viewBox {naive.get('viewBox')}->{occt.get('viewBox')}")
    if naive.get("fills") != occt.get("fills"):
        bits.append(f"fills {naive.get('fills')}->{occt.get('fills')}")

    return "  ".join(bits)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=str(MANIFEST))
    ap.add_argument("--only", help="substring filter on the part id")
    ap.add_argument("--out", help="write full per-part JSON results here")
    ap.add_argument("--work", default=None, help="scratch dir (default: temp under /tmp)")
    args = ap.parse_args(argv)

    parts, cli_args = load_outline_parts(Path(args.manifest))
    if args.only:
        parts = [p for p in parts if args.only in p]

    work = Path(args.work) if args.work else Path("/tmp/compare-engines-work")
    work.mkdir(parents=True, exist_ok=True)

    results = []
    failures = []
    for i, part in enumerate(parts, 1):
        t0 = time.time()
        naive_svg, naive_err = render(part, cli_args, "naive", work)
        naive_summary = {"error": naive_err} if naive_err else goldens.summarize_svg(naive_svg)

        occt_svg, occt_err = render(part, cli_args, "occt", work)
        occt_summary = {"error": occt_err} if occt_err else goldens.summarize_svg(occt_svg)

        if naive_err:
            failures.append((part, "naive", naive_err))
        if occt_err:
            failures.append((part, "occt", occt_err))

        results.append({"part": part, "naive": naive_summary, "occt": occt_summary})
        dt = time.time() - t0
        print(f"{i}/{len(parts)} {part}  {dt:5.1f}s  {line_for(part, naive_summary, occt_summary)}",
              flush=True)

    print(f"\n{len(parts)} parts, {len(failures)} render failures")
    if failures:
        for part, engine, err in failures:
            print(f"  FAILED {part} ({engine}): {err}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
        print(f"wrote {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
