#!/usr/bin/env python
"""Where an occt edge is lost: HLR, the authored-locus match, or a later drop.

Runs one part through `occt.visible_segments` with each stage recorded, and
writes an SVG in HLR's own 2-D frame (y up, so it reads upside down beside a
render; pass --flip to mirror it): every visible crease fragment HLR returned
in light gray, the outline compound in green, fragments matched to an
authored locus but later dropped in red, and what is drawn in black. Prints,
per authored locus with any fragment on it, how long the fragments are at
each stage.

Usage: probe-occt-stages.py 24434 --svg out/probe/occt-stages.svg
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brick_icons import cli, hlr, occt  # noqa: E402


def pts_of(edge):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    c = BRepAdaptor_Curve(edge)
    ts = np.linspace(c.FirstParameter(), c.LastParameter(), 24)
    return np.array([(c.Value(float(t)).X(), c.Value(float(t)).Y()) for t in ts])


def length(P):
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


def describe(locus):
    if locus[0] == "seg":
        return (f"seg {locus[3]} ({locus[1][0]:7.2f},{locus[1][1]:7.2f})->"
                f"({locus[2][0]:7.2f},{locus[2][1]:7.2f})")
    M = np.linalg.inv(locus[2])
    return (f"ell {locus[3]} c=({locus[1][0]:7.2f},{locus[1][1]:7.2f}) "
            f"axes=({np.hypot(*M[:, 0]):6.2f},{np.hypot(*M[:, 1]):6.2f})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("part")
    ap.add_argument("--svg", type=Path, required=True)
    ap.add_argument("--flip", action="store_true")
    args = ap.parse_args()

    rec = {}
    wrap = {}

    def spy(name, key):
        original = getattr(occt, name)
        wrap[name] = original

        def f(*a, **k):
            r = original(*a, **k)
            rec[key] = r
            if name == "select_authored" and "picked" not in rec:
                rec["picked"] = r
            return r
        setattr(occt, name, f)

    spy("hlr_edges", "comps")
    spy("authored_loci", "loci")
    spy("select_authored", "_sel")
    spy("_drop_lines_hlr_hides", "after_lines")
    spy("_drop_tangent_seams", "after_seams")

    cull = hlr.cull_orphan_runs

    def cull_spy(segs, *a, **k):
        kept = cull(segs, *a, **k)
        rec["cull"] = (list(segs), kept)
        return kept
    hlr.cull_orphan_runs = cull_spy
    cfg = cli._config_from_args(cli.build_parser().parse_args(
        [args.part, "--engine", "occt"]))
    hlr.visible_segments(args.part, cfg.ldraw_dir, lat=30.0, long=45.0,
                         render_px=900, engine="occt")
    for name, original in wrap.items():
        setattr(occt, name, original)
    hlr.cull_orphan_runs = cull

    before, after = rec["cull"]
    survived = {id(op) for op in after}
    for op in before:
        if id(op) in survived:
            continue
        if op[0] == "line":
            ends = f"({op[1]:7.2f},{op[2]:7.2f})->({op[3]:7.2f},{op[4]:7.2f})"
        else:
            e = hlr.primitives.arc_ellipse(op)
            a, b = e.point(np.radians(op[7])), e.point(np.radians(op[8]))
            ends = (f"({a[0]:7.2f},{a[1]:7.2f})->({b[0]:7.2f},{b[1]:7.2f}) "
                    f"deg {op[7]:.1f}..{op[8]:.1f}")
        print(f"orphan cull removed {op[0]} {op[-1]} {ends}")

    comps = rec["comps"]
    loci = rec["loci"]
    picked = rec["picked"]
    after_lines = rec.get("after_lines", picked)
    final = rec.get("after_seams", after_lines)
    kept_lines = {id(e) for e, _l in after_lines}
    kept_final = {id(e) for e, _l in final}

    sharp = [pts_of(e) for e in occt._edges_of(comps.get("sharp"))] \
        if comps.get("sharp") is not None else []
    outline = [pts_of(e) for e in occt._edges_of(comps.get("outline"))] \
        if comps.get("outline") is not None else []
    print(f"{len(sharp)} visible crease fragments, {len(outline)} outline, "
          f"{len(loci)} loci, {len(picked)} matched, {len(after_lines)} after "
          f"line mask, {len(final)} after seam veto")

    per = {}
    for e, l in picked:
        P = pts_of(e)
        row = per.setdefault(id(l), [l, 0.0, 0.0, 0.0])
        row[1] += length(P)
        row[2] += length(P) if id(e) in kept_lines else 0.0
        row[3] += length(P) if id(e) in kept_final else 0.0
    for i, (l, m, a, f) in enumerate(per.values()):
        flag = "" if abs(m - f) < 1e-6 else "  <-- dropped"
        print(f"[{i:3d}] matched {m:7.2f} line-mask {a:7.2f} drawn {f:7.2f}  "
              f"{describe(l)}{flag}")

    allp = np.vstack(sharp + outline) if sharp or outline else np.zeros((1, 2))
    lo, hi = allp.min(0), allp.max(0)
    W = 900.0
    s = (W - 40) / max(hi - lo)

    def tx(P):
        x = 20 + (P[:, 0] - lo[0]) * s
        y = 20 + (hi[1] - P[:, 1]) * s if not args.flip else \
            20 + (P[:, 1] - lo[1]) * s
        return np.stack([x, y], 1)

    body = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" '
            f'height="{W:.0f}" viewBox="0 0 {W:.0f} {W:.0f}">',
            '<rect width="100%" height="100%" fill="white"/>']

    def path(P, color, w):
        Q = tx(P)
        d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in Q)
        body.append(f'<path d="{d}" fill="none" stroke="{color}" '
                    f'stroke-width="{w}"/>')

    for P in sharp:
        path(P, "#d0d0d0", 4)
    for P in outline:
        path(P, "#2e9d3a", 2)
    for i, (e, _l) in enumerate(picked):
        P = pts_of(e)
        path(P, "#111" if id(e) in kept_final else "#d81b1b", 2)
    body.append("</svg>")
    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text("\n".join(body))
    print(f"wrote {args.svg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
