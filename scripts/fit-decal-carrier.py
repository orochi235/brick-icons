#!/usr/bin/env python
"""Whether a shattered print's own vertices lie on ONE surface.

A print that binds to facet planes comes back as many groups and draws
nothing. If the shards' vertices fit a single surface, the shards are one
decal cut up by the author's faceting and a synthesized carrier reassembles
them; if nothing fits, the carrier is a freeform sculpt and there is no one
surface to unwrap onto.

Fitted from the DECORATION's own polygons, never from the body: the print is
authored as one overlay, so its vertices are a declared set. Candidates are
a plane, a sphere, and a cone of revolution about each principal axis --
LDraw moulds are axis-aligned, and a general axis fit would report a surface
for point clouds that have none.

    scripts/fit-decal-carrier.py --out out/decal-carrier-fit.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from brick_icons.hlr import part_geometry  # noqa: E402

BODY_COLORS = {16, 24, "16", "24"}

#: LDU a vertex may sit off the fitted surface, at the 95th percentile. A
#: printed detail runs about an LDU wide, so a quarter of one is well inside
#: what the print itself resolves.
FIT_TOL = 0.25


def decoration(pid: str, ldraw: str) -> np.ndarray:
    tri, colors, _analytic = part_geometry(pid, ldraw)
    pts = [np.asarray(t, float).reshape(-1, 3)
           for t, c in zip(tri, colors) if c not in BODY_COLORS]
    if not pts:
        return np.zeros((0, 3))
    return np.unique(np.round(np.vstack(pts), 4), axis=0)


def _p95(d) -> float:
    return float(np.percentile(np.abs(d), 95))


def _plane_from(Q):
    c = Q.mean(0)
    _u, _s, vt = np.linalg.svd(Q - c, full_matrices=False)
    n = vt[2]
    return lambda P: np.abs((P - c) @ n)


def _sphere_from(Q):
    A = np.hstack([2 * Q, np.ones((len(Q), 1))])
    x, *_ = np.linalg.lstsq(A, (Q ** 2).sum(1), rcond=None)
    c, r2 = x[:3], x[3] + x[:3] @ x[:3]
    if not np.isfinite(r2) or r2 <= 0:
        return None
    r = np.sqrt(r2)
    return lambda P: np.abs(np.linalg.norm(P - c, axis=1) - r)


def _revolution_from(Q, axis):
    """r = a*h + b about `axis` through the ORIGIN -- a cone, and a cylinder
    where a is 0. LDraw models a mould on its own axis, so the axis LINE is
    not a free parameter; letting it float fits a surface through any three
    points and reports a revolution for point clouds that have none."""
    a = np.asarray(axis, float)

    def radial(X):
        h = X @ a
        return h, np.linalg.norm(X - np.outer(h, a), axis=1)

    hq, rq = radial(Q)
    if np.ptp(hq) < 1e-9:
        return None
    x, *_ = np.linalg.lstsq(np.column_stack([hq, np.ones(len(hq))]), rq,
                            rcond=None)

    def dist(P):
        h, r = radial(P)
        return np.abs(r - (x[0] * h + x[1]))
    return dist


def _cylinder_from(Q, axis):
    """A cylinder about `axis` whose LINE is fitted -- the case a mould off
    the origin needs, and the only one worth a position fit: a circle in the
    perpendicular projection is linear, a cone's apex is not."""
    a = np.asarray(axis, float)
    D = Q - np.outer(Q @ a, a)
    e1 = np.array([a[1], a[2], a[0]], float)
    e1 = e1 - a * (e1 @ a)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(a, e1)
    uv = np.column_stack([D @ e1, D @ e2])
    A = np.hstack([2 * uv, np.ones((len(uv), 1))])
    x, *_ = np.linalg.lstsq(A, (uv ** 2).sum(1), rcond=None)
    c, r2 = x[:2], x[2] + x[:2] @ x[:2]
    if not np.isfinite(r2) or r2 <= 0:
        return None
    r = np.sqrt(r2)

    def dist(P):
        E = P - np.outer(P @ a, a)
        w = np.column_stack([E @ e1, E @ e2])
        return np.abs(np.linalg.norm(w - c, axis=1) - r)
    return dist


AXES = (("x", (1., 0., 0.)), ("y", (0., 1., 0.)), ("z", (0., 0., 1.)))

#: (name, minimal sample size, fit). A minimal sample and a vote, not one
#: least-squares over everything: a part printed front and back has its
#: global fit dragged between two surfaces and lands on neither, reporting no
#: surface for a print that sits squarely on one.
FAMILIES = ([("plane", 3, _plane_from), ("sphere", 4, _sphere_from)]
            + [(f"revolution about {n}", 3,
                (lambda Q, a=a: _revolution_from(Q, a))) for n, a in AXES]
            + [(f"cylinder about {n}", 4,
                (lambda Q, a=a: _cylinder_from(Q, a))) for n, a in AXES])

TRIALS = 200


def _consensus(P, size, fit, rng) -> tuple[float, float]:
    """(largest share of the print one surface of this family holds, its p95
    residual), by RANSAC over minimal samples."""
    best_in = np.zeros(len(P), bool)
    for _ in range(TRIALS):
        dist = fit(P[rng.choice(len(P), size, replace=False)])
        if dist is None:
            continue
        near = dist(P) <= FIT_TOL
        if near.sum() > best_in.sum():
            best_in = near
    if best_in.sum() < 8:
        return 0.0, float("inf")
    dist = fit(P[best_in])                      # refit on the consensus
    if dist is None:
        return 0.0, float("inf")
    d = dist(P)
    near = d <= FIT_TOL
    return float(near.mean()), _p95(d[near]) if near.any() else float("inf")


def classify(P, seed: int = 0) -> tuple[str, float, float]:
    """(surface, share of the print it holds, that share's p95 residual)."""
    if len(P) < 8:
        return "too few points", 0.0, float("inf")
    rng = np.random.default_rng(seed)
    best = ("no single surface", 0.0, float("inf"))
    for name, size, fit in FAMILIES:
        share, resid = _consensus(P, size, fit, rng)
        if share > best[1]:
            best = (name, share, resid)
    return best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ldraw", default="vendor/ldraw")
    ap.add_argument("--drop", default="out/decal-drop.csv",
                    help="triage-decal-drop.py output; its parts are the set")
    ap.add_argument("--parts", nargs="*", help="parts to fit instead")
    ap.add_argument("--gates", default="more groups than the cap,"
                    "shattered across facets")
    ap.add_argument("--out", default="out/decal-carrier-fit.csv")
    args = ap.parse_args(argv)

    if args.parts:
        picks = [(p, "") for p in args.parts]
    else:
        gates = set(args.gates.split(","))
        picks = [(r["part_id"], r["gate"])
                 for r in csv.DictReader(open(args.drop))
                 if r["gate"] in gates]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tally: dict[str, int] = {}
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["part_id", "gate", "fit", "share", "resid_p95",
                    "points", "secs"])
        for i, (pid, gate) in enumerate(picks, 1):
            t0 = time.time()
            try:
                P = decoration(pid, args.ldraw)
                fit, share, resid = classify(P)
            except Exception as exc:
                P = np.zeros((0, 3))
                fit, share, resid = f"error: {type(exc).__name__}", 0.0, 0.0
            secs = time.time() - t0
            bucket = fit if share >= 0.9 else "no single surface"
            tally[bucket] = tally.get(bucket, 0) + 1
            w.writerow([pid, gate, fit, f"{share:.3f}", f"{resid:.3f}",
                        len(P), f"{secs:.2f}"])
            fh.flush()
            print(f"{i}/{len(picks)}  {pid:16s} {fit} holds {share:6.1%} "
                  f"({resid:.3f} LDU, {secs:.1f}s)", flush=True)

    print(f"\n{len(picks)} parts -> {out}  (a surface counts where it "
          f"holds 90% of the print)")
    for fit, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {n:6d}  {fit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
