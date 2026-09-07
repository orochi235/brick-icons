#!/usr/bin/env python3
"""Which parts `b350c40` changes: HLR run twice per part, shell against loose
faces, and the visible edge sets compared.

    .venv/bin/python scripts/hlr-shell-affected.py --list out/census/parts.txt \
        --out restage/hlr-loose-faces.txt

Cheaper than rendering each part twice -- it stops after HLR and never builds
fills, arcs or SVG, 0.3s a part against up to 40s. What comes out is the
re-render list for the occt slot:

    .venv/bin/python scripts/build-render-store.py --list restage/... \
        --sources occt --force

It is a SUPERSET, deliberately. Checked against a full render A/B of 160
sampled parts it caught all 49 whose SVG changed and named 13 more that did
not -- a wasted re-render costs a few seconds, a missed one leaves a stale
drawing on the wall.

One pose (iso, what every canonical slot draws). A part whose drawing moves at
some other angle and not at iso is missed, and nothing here can find it short
of sweeping poses.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import occt  # noqa: E402
from brick_icons.hlr import view_basis  # noqa: E402


def edge_key(comps) -> tuple:
    """Every visible edge as a rounded tuple, in the order HLR hands them back.

    Order counts. Sorting first looked like the honest comparison and missed 9
    of 33 parts whose pixels move: the stages below HLR read the ops in
    sequence, so the same edges in a different order can still trace
    differently.
    """
    out = []
    for name in ("sharp", "outline"):
        comp = comps.get(name)
        if comp is None:
            continue
        for edge in occt._edges_of(comp):
            for op in occt._edge_ops(edge, name):
                out.append(tuple([op[0]] + [round(float(v), 4) for v in op[1:-1]]))
    return tuple(out)


def moves(part: str, ldraw_dir, lat: float, long: float) -> bool:
    right, up = view_basis(lat, long)[:2]
    shape = occt.build_shape(occt.flatten_part(part, ldraw_dir))
    real = occt._loose_faces
    try:
        occt._loose_faces = lambda s: s
        before = edge_key(occt.hlr_edges(shape, right, up))
        occt._loose_faces = real
        after = edge_key(occt.hlr_edges(shape, right, up))
    finally:
        occt._loose_faces = real
    return before != after


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list")
    ap.add_argument("--ldraw-dir", default="vendor/ldraw")
    ap.add_argument("--angle", default="30,45")
    ap.add_argument("--out", help="write the affected part ids here")
    ap.add_argument("--log", help="one JSON line per part; resumes from it")
    a = ap.parse_args(argv)

    ids = list(a.parts)
    if a.list:
        ids += [s for line in Path(a.list).read_text().splitlines()
                if (s := line.split("#")[0].strip())]
    if not ids:
        ap.error("name at least one part, or pass --list")
    lat, long = (float(v) for v in a.angle.split(","))

    # A part OCCT hangs on takes the run with it, so the log is the resume
    # point: relaunch with the same --log and it picks up where it stopped.
    done: dict[str, bool] = {}
    log = Path(a.log) if a.log else None
    if log and log.exists():
        for line in log.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if "moves" in row:
                done[row["part"]] = row["moves"]

    hit, err, n = [], [], len(ids)
    for i, part in enumerate(ids, 1):
        t = time.time()
        if part in done:
            if done[part]:
                hit.append(part)
            continue
        try:
            changed = moves(part, a.ldraw_dir, lat, long)
        except Exception as exc:
            err.append(part)
            row = {"part": part, "error": f"{type(exc).__name__}: {exc}"}
            print(f"{i}/{n} {part}: ERROR {row['error'][:80]}", flush=True)
        else:
            if changed:
                hit.append(part)
            row = {"part": part, "moves": changed}
            print(f"{i}/{n} {part}: {'MOVES' if changed else 'same'} "
                  f"({time.time() - t:.1f}s)", flush=True)
        if log:
            with log.open("a") as fh:
                fh.write(json.dumps(row) + "\n")

    print(f"\nmoves {len(hit)}/{n}; errors {len(err)}", flush=True)
    if a.out:
        head = (f"# Parts whose occt drawing b350c40 moves, at iso.\n"
                f"# {len(hit)} of {n} checked, {len(err)} could not be read.\n"
                f"# scripts/hlr-shell-affected.py wrote this; re-derive rather\n"
                f"# than hand-edit. Feed it to build-render-store.py --force.\n")
        Path(a.out).write_text(head + "".join(p + "\n" for p in hit))
        print(f"wrote {a.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
