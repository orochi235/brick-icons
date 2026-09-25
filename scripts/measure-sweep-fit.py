"""How closely sweep.py's frustum chain matches each tube the part authored.

    .venv/bin/python scripts/measure-sweep-fit.py 3127a 2583 87748

Per part, maxima over its tubes, all as a fraction of the ring radius r:
ring fit is how far authored ring vertices stray from their fitted circle;
verts off is how far they sit from the adjacent frustums' surfaces; joint gap
is how far apart two neighboring frustums' sections are in their shared ring
plane (what OCCT has to sew); oversize is how much wider that section is than
the ring. Measured on the analytic frustums, before OCCT builds them.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from brick_icons import hlr, sweep  # noqa: E402


def surface_offset(p, cone):
    c0, a, h, r0, r1 = cone
    s = (p - c0) @ a
    rho = np.linalg.norm(p - c0 - s * a)
    return (rho - (r0 + (r1 - r0) * s / h)) * h / math.hypot(h, r1 - r0)


def reach(c, d, cone):
    """Distance from c along d to the cone's surface."""
    lo, hi = 0.0, 10 * max(cone[3], cone[4]) + 1
    for _ in range(80):
        m = (lo + hi) / 2
        lo, hi = (lo, m) if surface_offset(c + m * d, cone) > 0 else (m, hi)
    return (lo + hi) / 2


def measure(part, roots):
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3), out, roots)
    found, quads = sweep.tubes(out)
    pts = {k: np.asarray(p, float) for _, keys, ps, _m in quads for k, p in zip(keys, ps)}
    m = dict(tubes=len(found), frustums=0, fit=0.0, off=0.0, gap=0.0, over=0.0)
    for rings, _qis in found:
        cones = []
        for (c0, r0, _n0, _), (c1, r1, _n1, _) in zip(rings, rings[1:]):
            h = np.linalg.norm(c1 - c0)
            cones.append((c0, (c1 - c0) / h, h, r0, r1))
        m["frustums"] += len(cones)
        for i, (c, r, n, vs) in enumerate(rings):
            P = np.array([pts[k] for k in vs])
            m["fit"] = max(m["fit"], np.abs(np.linalg.norm(P - c, axis=1) - r).max() / r)
            for cone in cones[max(i - 1, 0):i + 1]:
                m["off"] = max(m["off"], max(abs(surface_offset(p, cone)) for p in P) / r)
            if 0 < i < len(cones):
                u = np.cross(n, [1, 0, 0] if abs(n[0]) < .9 else [0, 1, 0])
                u /= np.linalg.norm(u)
                v = np.cross(n, u)
                for th in np.linspace(0, 2 * math.pi, 72, endpoint=False):
                    d = math.cos(th) * u + math.sin(th) * v
                    ta, tb = reach(c, d, cones[i - 1]), reach(c, d, cones[i])
                    m["gap"] = max(m["gap"], abs(ta - tb) / r)
                    m["over"] = max(m["over"], max(ta, tb) / r - 1)
    return m


def main():
    roots = hlr.default_roots("vendor/ldraw")
    print(f"{'part':8} {'tubes':>5} {'frust':>5} {'ring fit':>8} {'verts off':>9} "
          f"{'joint gap':>9} {'oversize':>8}")
    for part in sys.argv[1:]:
        m = measure(part, roots)
        print(f"{part:8} {m['tubes']:5d} {m['frustums']:5d} {100 * m['fit']:7.2f}% "
              f"{100 * m['off']:8.2f}% {100 * m['gap']:8.2f}% {100 * m['over']:7.2f}%",
              flush=True)


main()
