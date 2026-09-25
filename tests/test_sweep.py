"""A hand-authored ring-quad tube becomes a chain of exact frustums; a dish,
a nut and an undeclared strip do not."""
import math

import numpy as np
import pytest

from brick_icons import hlr, sweep


def _ring(center, radius, axis, n):
    axis = np.asarray(axis, float) / np.linalg.norm(axis)
    ref = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(axis, ref)
    u /= np.linalg.norm(u)
    v = np.cross(axis, u)
    return [np.asarray(center, float) + radius * (math.cos(t) * u + math.sin(t) * v)
            for t in np.linspace(0, 2 * math.pi, n, endpoint=False)]


def _write(path, rings, condlines=True):
    """A .dat of quads between consecutive rings, with a conditional line
    along every spine edge when asked."""
    lines = ["0 BFC CERTIFY CCW"]
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for j in range(n):
            k = (j + 1) % n
            p = [a[j], a[k], b[k], b[j]]
            lines.append("4 16 " + " ".join(f"{c:.4f}" for q in p for c in q))
            if condlines:
                ctl = [a[j], b[j], a[k], a[(j - 1) % n]]
                lines.append("5 24 " + " ".join(f"{c:.4f}" for q in ctl for c in q))
    path.write_text("\n".join(lines) + "\n")


def _flatten(path):
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(path, np.eye(3), np.zeros(3), out, [path.parent])
    return out


def test_a_bent_declared_tube_becomes_frustums(tmp_path):
    """Nine rings on a quarter circle, each perpendicular to its own tangent,
    every spine edge declared smooth: one tube of eight frustums, its quads
    gone, its spine condlines gone, its ring chords kept."""
    rings = []
    for k in range(9):
        t = math.radians(90 * k / 8)
        c = np.array([40 * math.cos(t), 40 * math.sin(t), 0.0])
        tangent = np.array([-math.sin(t), math.cos(t), 0.0])
        rings.append(_ring(c, 4.0, tangent, 16))
    p = tmp_path / "tube.dat"
    _write(p, rings)
    out = _flatten(p)
    tris, cond = len(out["tri"]), len(out["5"])
    assert sweep.substitute(out) == 1
    frustums = [q for q in out["analytic"] if getattr(q, "sweep", False)]
    assert len(frustums) == 8
    assert all(q.kind == "cyli" for q in frustums), "constant radius is a cylinder"
    assert all(getattr(q, "cut", None) for q in frustums), "cut to its ring planes"
    assert len(out["tri"]) == tris - 8 * 16 * 2
    assert len(out["5"]) == cond - 8 * 16, "the spine condlines are gone"
    assert len(out["tri_meta"]) == len(out["tri"])


def test_a_tapering_tube_becomes_cones(tmp_path):
    rings = [_ring([0, 0, 20 * k], 6.0 - 0.5 * k, [0, 0, 1], 12) for k in range(4)]
    p = tmp_path / "taper.dat"
    _write(p, rings)
    out = _flatten(p)
    assert sweep.substitute(out) == 1
    assert [q.kind for q in out["analytic"]] == ["con"] * 3


def test_a_dish_of_concentric_rings_is_not_a_tube(tmp_path):
    """Radius collapsing toward the pole faster than the rings advance is a
    dome, and the shading already knows how to draw one of those."""
    rings = [_ring([0, 0, 2 * k], 20.0 - 5.0 * k, [0, 0, 1], 16) for k in range(4)]
    p = tmp_path / "dish.dat"
    _write(p, rings)
    out = _flatten(p)
    assert sweep.substitute(out) == 0
    assert not out["analytic"]


def test_a_nut_declares_no_seam_and_stays_faceted(tmp_path):
    rings = [_ring([0, 0, 0], 6.0, [0, 0, 1], 6), _ring([0, 0, 8], 6.0, [0, 0, 1], 6)]
    p = tmp_path / "nut.dat"
    _write(p, rings, condlines=False)
    out = _flatten(p)
    assert sweep.substitute(out) == 0


def test_disarmed_leaves_everything(tmp_path):
    rings = [_ring([0, 0, 8 * k], 4.0, [0, 0, 1], 8) for k in range(3)]
    p = tmp_path / "tube.dat"
    _write(p, rings)
    out = _flatten(p)
    tris = len(out["tri"])
    sweep.SUBSTITUTE = False
    try:
        assert sweep.substitute(out) == 0
    finally:
        sweep.SUBSTITUTE = True
    assert len(out["tri"]) == tris


@pytest.mark.parametrize("part, tubes", [("3127a", 1), ("3127b", 1), ("3960", 0)])
def test_library_parts(part, tubes):
    """3127a's hook is one declared tube; 3960's dish is rings too, and is
    not one."""
    roots = hlr.default_roots("vendor/ldraw")
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(hlr._resolve_input(part, roots), np.eye(3), np.zeros(3), out, roots)
    assert sweep.substitute(out) == tubes
