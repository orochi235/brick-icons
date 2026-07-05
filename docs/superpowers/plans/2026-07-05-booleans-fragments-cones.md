# Polygon Booleans + Fragment Clipping + Analytic Cones/ndis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One SVG element per visible surface: robust 2-D booleans (shapely) merge smooth/coplanar facet groups and clip every fill to its visible fragment; analytic `con`/`ndis` substitution removes cone facet clouds at the source.

**Architecture:** New `geom2d.py` isolates shapely (clean/union/difference/path-d). `primitives.py` gains `con`+`ndis` parsing, `ConeOccluder` (local-frame quadric), `NdisOccluder`. `shade.py` builds cone wall faces (generalized from cylinder helpers) and ndis flat faces, stamps facet-group ids, and rewrites `fill_ops` to clip nearest-first then union per group. `trace.py` fills get `fill-rule="evenodd"`. `hlr.py` only wires new occluders + fit points.

**Tech Stack:** Python 3.11, numpy, shapely 2.x (new dep), pytest. Spec: `docs/superpowers/specs/2026-07-05-booleans-fragments-cones-design.md`.

**Status: EXECUTED 2026-07-05** (inline, task by task, TDD; commits a8c4087..).
Deviations discovered during validation — see the spec's "Implementation
notes (as built)": ndis substitution reverted (tone-continuity with facet
groups beats analytic exactness there); smooth-joint rim arcs suppressed via
`wall_rims`/`skip_rims` (full-sector, equal-slope, opposite-side rule).

**Conventions:** venv at `.venv`; run tests as `.venv/bin/python -m pytest tests/... -q`. Vendor-gated tests follow the existing skip pattern in `tests/test_hlr.py`. Commit after every task with the trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: shapely dep + `geom2d.py`

**Files:**
- Modify: `pyproject.toml` (dependencies)
- Create: `brick_icons/geom2d.py`
- Create: `tests/test_geom2d.py`

- [ ] **Step 1.1: Install dep**

`pyproject.toml`: `dependencies = ["pillow>=10", "numpy>=1.26", "shapely>=2.0"]`
Run: `.venv/bin/pip install shapely` → installs OK; `.venv/bin/python -c "import shapely; print(shapely.__version__)"` prints 2.x.

- [ ] **Step 1.2: Write failing tests** (`tests/test_geom2d.py`)

```python
import numpy as np
from brick_icons import geom2d


def sq(x0, y0, x1, y1):
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float)


def test_tjunction_union_is_one_polygon():
    # bottom rect + top rect split in two (T-junction at (1,1)): union must be
    # ONE polygon of exact area — the 3960 dish 16-vs-48 ring case in miniature.
    a = geom2d.to_geom(sq(0, 0, 2, 1))
    b1 = geom2d.to_geom(sq(0, 1, 1, 2))
    b2 = geom2d.to_geom(sq(1, 1, 2, 2))
    u = geom2d.union_all([a, b1, b2])
    assert u.geom_type == "Polygon"
    assert abs(geom2d.area(u) - 4.0) < 1e-6


def test_self_overlap_union():
    u = geom2d.union_all([geom2d.to_geom(sq(0, 0, 2, 2)),
                          geom2d.to_geom(sq(1, 0, 3, 2))])
    assert abs(geom2d.area(u) - 6.0) < 1e-6


def test_difference_makes_hole_and_two_subpaths():
    outer = geom2d.to_geom(sq(0, 0, 4, 4))
    inner = geom2d.to_geom(sq(1, 1, 3, 3))
    d_geom = geom2d.difference(outer, inner)
    assert abs(geom2d.area(d_geom) - 12.0) < 1e-6
    d = geom2d.path_d(d_geom)
    assert d.count("M ") == 2 and d.count("Z") == 2


def test_holes_via_to_geom():
    g = geom2d.to_geom(sq(0, 0, 4, 4), holes=[sq(1, 1, 3, 3)])
    assert abs(geom2d.area(g) - 12.0) < 1e-6


def test_degenerate_inputs_never_raise():
    assert geom2d.area(geom2d.to_geom(np.array([(0, 0), (1, 1)], float))) == 0.0
    collinear = np.array([(0, 0), (1, 0), (2, 0)], float)
    assert geom2d.area(geom2d.to_geom(collinear)) == 0.0
    keyhole = np.array([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0),
                        (1, 1), (1, 3), (3, 3), (3, 1), (1, 1)], float)
    g = geom2d.to_geom(keyhole)          # self-touching: must clean, not raise
    assert geom2d.area(g) > 0


def test_multipolygon_path_d():
    u = geom2d.union_all([geom2d.to_geom(sq(0, 0, 1, 1)),
                          geom2d.to_geom(sq(5, 5, 6, 6))])
    d = geom2d.path_d(u)
    assert d.count("M ") == 2
```

Run: `.venv/bin/python -m pytest tests/test_geom2d.py -q` → FAIL (no module `geom2d`).

- [ ] **Step 1.3: Implement** (`brick_icons/geom2d.py`)

```python
"""Robust 2-D polygon booleans for fill fragments (shapely/GEOS isolated here).

Used by shade.fill_ops to (a) union smooth-group / coplanar facet polygons into
one region per surface and (b) clip each face to its visible fragment. All
coordinates are output-canvas px. Any GEOS failure degrades to an empty/original
geometry — a degenerate sliver must never kill a render.
"""
from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import Polygon

GRID = 1e-3            # set_precision snap grid, px


def _only_area(g):
    """Keep only polygonal content (make_valid can emit lines/points)."""
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    if hasattr(g, "geoms"):
        polys = [x for x in g.geoms if x.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(polys) if polys else Polygon()
    return Polygon()


def to_geom(poly, holes=None):
    """ndarray ring (+ optional hole rings) -> cleaned shapely polygon."""
    try:
        p = np.asarray(poly, float)
        if len(p) < 3:
            return Polygon()
        g = Polygon(p, [np.asarray(h, float) for h in (holes or []) if len(h) >= 3])
        g = shapely.set_precision(g, GRID)
        if not g.is_valid:
            g = shapely.make_valid(g)
        return _only_area(g)
    except Exception:
        return Polygon()


def union(a, b):
    try:
        return _only_area(shapely.union(a, b))
    except Exception:
        return a


def union_all(geoms):
    gs = [g for g in geoms if g is not None and not g.is_empty]
    if not gs:
        return Polygon()
    try:
        return _only_area(shapely.union_all(gs))
    except Exception:
        return gs[0]


def difference(a, b):
    try:
        return _only_area(shapely.difference(a, b))
    except Exception:
        return a


def area(g):
    return 0.0 if g is None else float(g.area)


def path_d(g):
    """Polygon/MultiPolygon -> one SVG path 'd' (one subpath per ring).
    Pair with fill-rule="evenodd" so interior rings render as holes."""
    if g is None or g.is_empty:
        return ""
    polys = list(getattr(g, "geoms", [g]))
    cmds = []
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        for ring in [p.exterior, *p.interiors]:
            pts = list(ring.coords)[:-1]
            if len(pts) < 3:
                continue
            cmds.append("M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) + " Z")
    return " ".join(cmds)
```

- [ ] **Step 1.4: Run** `.venv/bin/python -m pytest tests/test_geom2d.py -q` → all PASS.
- [ ] **Step 1.5: Commit** `feat(geom2d): shapely wrapper — clean, union, difference, path-d`

---

### Task 2: `parse_primitive` learns `con` and `ndis`

**Files:**
- Modify: `brick_icons/primitives.py:22-46`
- Test: `tests/test_primitives.py`

- [ ] **Step 2.1: Failing tests** (append to `tests/test_primitives.py`)

```python
def test_parse_cone_names():
    assert primitives.parse_primitive("4-4con4.dat") == ("con", 360.0, 4)
    assert primitives.parse_primitive("1-4con0.dat") == ("con", 90.0, 0)
    assert primitives.parse_primitive("1-16con13.dat") == ("con", 22.5, 13)
    assert primitives.parse_primitive("48\\4-4con3.dat") == ("con", 360.0, 3)


def test_parse_ndis_names():
    assert primitives.parse_primitive("4-4ndis.dat") == ("ndis", 360.0, 0)
    assert primitives.parse_primitive("1-4ndis.dat") == ("ndis", 90.0, 0)


def test_parse_still_rejects_unhandled():
    for name in ("1-16tndis.dat", "1-4cyls.dat", "1-8chrd.dat", "4-4con.dat"):
        assert primitives.parse_primitive(name) is None
```

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q` → new tests FAIL.

- [ ] **Step 2.2: Implement.** In `primitives.py` change the regex and parser:

```python
_FRAC = re.compile(r"^(\d+)-(\d+)(edge|cyli|cylo|disc|ndis|ring|con)(\d*)$")
```

In `parse_primitive`, after computing `sector`:

```python
    kind = "cyli" if fam == "cylo" else fam
    if kind == "con":
        if not suffix:
            return None            # 'conN' always carries its top radius
        return ("con", sector, int(suffix))
    inner = int(suffix) if (kind == "ring" and suffix) else 0
    if kind == "ring" and inner == 0:
        return None
    return (kind, sector, inner)
```

(where `fam`/`suffix` come from the existing match groups; docstring: kind now in
`{'edge','cyli','disc','ring','con','ndis'}`; for `con`, the third element is the
TOP radius N — geometry is radius N+1 at local y=0 tapering to N at y=1.)

- [ ] **Step 2.3: Run** the file's tests → PASS. **Guard:** `.venv/bin/python -m pytest -q` (whole suite) — `flatten` now routes con/ndis into `out["analytic"]`; downstream `faces_from_analytic`/occluder wiring ignores unknown kinds silently (`if occ is not None`), so nothing should break; fix any failure before committing.
- [ ] **Step 2.4: Commit** `feat(primitives): parse conN and ndis as analytic primitives`

---

### Task 3: `ConeOccluder`

**Files:**
- Modify: `brick_icons/primitives.py` (after `CylinderOccluder`)
- Test: `tests/test_primitives.py`

- [ ] **Step 3.1: Failing tests**

```python
def test_cone_occluder_axis_aligned_hit():
    # con0: radius 1 at y=0 -> 0 at y=1. Ray along +Z at (x=.25, y=.5):
    # radius there is .5, so hit at z = -sqrt(.25^2? no: x^2+z^2=r^2) ...
    occ = primitives.ConeOccluder(np.eye(3), np.zeros(3), 360.0, 0)
    O = np.array([[0.25, 0.5, -5.0]])
    F = np.array([0.0, 0.0, 1.0])
    z = math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(occ.depth(O, F)[0] - (5.0 - z)) < 1e-9
    assert abs(occ.depth_far(O, F)[0] - (5.0 + z)) < 1e-9


def test_cone_occluder_height_and_sector_clamp():
    occ = primitives.ConeOccluder(np.eye(3), np.zeros(3), 360.0, 0)
    assert not np.isfinite(occ.depth(np.array([[0.1, 1.5, -5.0]]),
                                     np.array([0.0, 0.0, 1.0]))[0])
    quarter = primitives.ConeOccluder(np.eye(3), np.zeros(3), 90.0, 0)
    # theta ~ 135deg (x<0, z>0) is outside [0,90]
    O = np.array([[-0.25, 0.5, -5.0]])
    d = quarter.depth(O, np.array([0.0, 0.0, 1.0]))[0]
    z = math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(d - (5.0 + z)) < 1e-9          # near hit (x<0,z<0) invalid; far one in-sector


def test_cone_occluder_scaled_transform():
    # radius x2, height x3, translated: hits scale exactly (lambda is invariant
    # under the linear map, so depths are world units).
    R = np.diag([2.0, 3.0, 2.0])
    t = np.array([10.0, 0.0, 0.0])
    occ = primitives.ConeOccluder(R, t, 360.0, 0)
    O = np.array([[10.5, 1.5, -9.0]])          # local (.25, .5): radius 2*.5=1 @ world
    F = np.array([0.0, 0.0, 1.0])
    z = 2.0 * math.sqrt(0.5 ** 2 - 0.25 ** 2)
    assert abs(occ.depth(O, F)[0] - (9.0 - z)) < 1e-9
```

(add `import math` at top of the test file if absent). Run → FAIL (`ConeOccluder` missing).

- [ ] **Step 3.2: Implement** (in `primitives.py`, mirroring `CylinderOccluder`'s API)

```python
class ConeOccluder:
    """Truncated cone: local radius (top+1) at y=0 tapering to `top` at y=1,
    under transform R, t; optional angular sector.

    Works in the primitive's LOCAL frame (Minv = R^-1) so scale and shear are
    exact; the ray parameter lambda is invariant under the linear map, so the
    returned depths are world units along F, same as the other occluders.
    """

    def __init__(self, R, t, sector, top):
        self.R = np.asarray(R, float)
        self.t = np.asarray(t, float)
        self.Minv = np.linalg.inv(self.R)
        self.sector = sector
        self.top = float(top)

    def _hits(self, O, F, clamp=True):
        O = np.atleast_2d(O).astype(float)
        o = (O - self.t) @ self.Minv.T
        f = self.Minv @ np.asarray(F, float)
        rb = self.top + 1.0                     # base radius, local units
        k = rb - o[:, 1]                        # radius at the ray origin's y
        a = f[0] * f[0] + f[2] * f[2] - f[1] * f[1]
        b = 2.0 * (o[:, 0] * f[0] + o[:, 2] * f[2] + k * f[1])
        c = o[:, 0] * o[:, 0] + o[:, 2] * o[:, 2] - k * k
        near = np.full(len(o), np.inf)
        far = np.full(len(o), -np.inf)
        if abs(a) < 1e-12:                      # ray parallel to a generator
            with np.errstate(divide="ignore", invalid="ignore"):
                lam = np.where(np.abs(b) > 1e-12, -c / b, np.inf)
            roots, ok = [lam], np.abs(b) > 1e-12
        else:
            disc = b * b - 4 * a * c
            ok = disc >= 0
            sq = np.sqrt(np.where(ok, disc, 0.0))
            roots = [(-b - sq) / (2 * a), (-b + sq) / (2 * a)]
        for lam in roots:
            P = o + lam[:, None] * f
            y = P[:, 1]
            if clamp:
                valid = (ok & np.isfinite(lam) & (y >= -1e-6) & (y <= 1 + 1e-6)
                         & _angle_in_sector(P[:, 0], P[:, 2], self.sector))
            else:
                valid = ok & np.isfinite(lam) & (rb - y >= 0)   # not the mirror nappe
            near = np.minimum(near, np.where(valid, lam, np.inf))
            far = np.maximum(far, np.where(valid, lam, -np.inf))
        return near, far

    def depth(self, O, F):
        return self._hits(O, F)[0]

    def depth_far(self, O, F, clamp=True):
        return self._hits(O, F, clamp=clamp)[1]
```

- [ ] **Step 3.3: Run** → PASS. **Commit** `feat(primitives): ConeOccluder — local-frame ray/cone quadric`

---

### Task 4: cone drawn ops (rim arcs + silhouette generators)

**Files:**
- Modify: `brick_icons/primitives.py` — `drawn_with_depth`
- Test: `tests/test_primitives.py`

The silhouette condition: local cone normal along a generator is constant,
`m(θ) = (cosθ, 1, sinθ)`; world condition `n·fwd = 0` reduces (via
`g = Minv @ fwd`) to `g0 cosθ + g2 sinθ = -g1`, i.e. `A cosθ + B sinθ = C`
with `(A, B, C) = (g0, g2, -g1)` → `θ = atan2(B, A) ± acos(C/hypot(A,B))`
(0, 1, or 2 solutions).

- [ ] **Step 4.1: Failing tests**

```python
def _stub_proj():
    # camera looks along -Z: A=x, B=y, depth=-z; identity pixel fit
    def to_AB(P):
        P = np.atleast_2d(np.asarray(P, float))
        return P[:, 0], P[:, 1], -P[:, 2]
    return to_AB, np.array([0.0, 0.0, -1.0])


def test_cone_drawn_ops_full_sector():
    to_AB, fwd = _stub_proj()
    rec = {"kind": "con", "sector": 360.0, "inner": 1, "R": np.eye(3), "t": np.zeros(3)}
    pairs = primitives.drawn_with_depth(rec, to_AB, 1.0, 0.0, 0.0, 0.0, fwd)
    ops = [op for op, *_ in pairs]
    arcs = [o for o in ops if o[0] == "arc"]
    sils = [o for o in ops if o[0] == "line" and o[-1] == "sil"]
    assert len(arcs) == 2 and len(sils) == 2
    # generators at theta = 0 and pi: base pts (+-2, 0), top pts (+-1, 1)
    ends = sorted((round(o[1], 6), round(o[3], 6)) for o in sils)
    assert ends == [(-2.0, -1.0), (2.0, 1.0)]


def test_cone_apex_no_top_arc():
    to_AB, fwd = _stub_proj()
    rec = {"kind": "con", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}
    ops = [op for op, *_ in primitives.drawn_with_depth(rec, to_AB, 1.0, 0.0, 0.0, 0.0, fwd)]
    assert len([o for o in ops if o[0] == "arc"]) == 1     # base rim only
    sils = [o for o in ops if o[0] == "line"]
    assert all(abs(o[3]) < 1e-9 and abs(o[4] - 1.0) < 1e-9 for o in sils)  # to apex (0,1)


def test_cone_axis_on_view_no_generators():
    def to_AB(P):
        P = np.atleast_2d(np.asarray(P, float))
        return P[:, 0], P[:, 2], -P[:, 1]
    fwd = np.array([0.0, -1.0, 0.0])           # looking down the cone axis
    rec = {"kind": "con", "sector": 360.0, "inner": 1, "R": np.eye(3), "t": np.zeros(3)}
    ops = [op for op, *_ in primitives.drawn_with_depth(rec, to_AB, 1.0, 0.0, 0.0, 0.0, fwd)]
    assert not [o for o in ops if o[0] == "line"]
```

Run → FAIL (con falls through, returns []).

- [ ] **Step 4.2: Implement.** In `drawn_with_depth`, add after the `cyli` branch:

```python
    elif kind == "con":
        R = np.asarray(R, float)
        N = float(rec["inner"])
        A3 = R[:, 1]
        fwd = np.asarray(fwd, float)
        base = project_circle(R, t, N + 1.0, to_AB, s, cx, cy, half)
        topc = (project_circle(R, np.asarray(t, float) + A3, N, to_AB, s, cx, cy, half)
                if N > 0 else None)
        if topc is None:                        # apex: project the point itself
            aa, bb, zz = to_AB((np.asarray(t, float) + A3)[None, :])
            apex_xy = ((aa[0] - cx) * s + half, (bb[0] - cy) * s + half)
            apex_z = float(zz[0])
        g = np.linalg.inv(R) @ fwd
        A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(A_, B_)
        if hyp > 1e-12 and abs(C_) <= hyp:
            phi0 = math.atan2(B_, A_)
            dth = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            for th in (phi0 + dth, phi0 - dth):
                deg = math.degrees(th) % 360.0
                if sector >= 360.0 - 1e-9 or deg <= sector + 1e-6:
                    pb = base.point(th)
                    if topc is not None:
                        pt_, zt = topc.point(th), topc.depth(th)
                    else:
                        pt_, zt = apex_xy, apex_z
                    op = ("line", float(pb[0]), float(pb[1]),
                          float(pt_[0]), float(pt_[1]), "sil")
                    pairs.append((op, _line_depth_fn(base.depth(th), zt)))
        pairs.append((_arc_op(base, 0.0, sector, "edge"), _arc_depth_fn(base)))
        if topc is not None:
            pairs.append((_arc_op(topc, 0.0, sector, "edge"), _arc_depth_fn(topc)))
```

- [ ] **Step 4.3: Run** → PASS. **Commit** `feat(primitives): cone rim arcs + silhouette generator lines`

---

### Task 5: `NdisOccluder`

**Files:**
- Modify: `brick_icons/primitives.py` (after `DiscOccluder`)
- Test: `tests/test_primitives.py`

- [ ] **Step 5.1: Failing tests**

```python
def test_ndis_occluder_region():
    occ = primitives.NdisOccluder(np.eye(3), np.zeros(3), 360.0)
    F = np.array([0.0, -1.0, 0.0])
    O = np.array([[0.99, 5.0, 0.99],    # corner: in square, outside disc -> hit
                  [0.5, 5.0, 0.5],      # inside disc -> miss
                  [1.2, 5.0, 0.0]])     # outside square -> miss
    d = occ.depth(O, F)
    assert abs(d[0] - 5.0) < 1e-9
    assert not np.isfinite(d[1]) and not np.isfinite(d[2])


def test_ndis_occluder_sector():
    occ = primitives.NdisOccluder(np.eye(3), np.zeros(3), 90.0)
    F = np.array([0.0, -1.0, 0.0])
    d = occ.depth(np.array([[0.99, 5.0, 0.99], [-0.99, 5.0, 0.99]]), F)
    assert np.isfinite(d[0]) and not np.isfinite(d[1])
```

Run → FAIL.

- [ ] **Step 5.2: Implement**

```python
class NdisOccluder:
    """Square-minus-disc corner fill in the local XZ plane (normal = axis A):
    inside the unit square, outside the unit disc, within the sector."""

    def __init__(self, R, t, sector):
        self.C = np.asarray(t, float)
        self.U, self.V, self.A, self.r, _ = _local_basis(R, t)
        self.n = self.A / (np.linalg.norm(self.A) or 1.0)
        self.sector = sector
        self.uhat = self.U / (self.r or 1.0)
        self.vhat = self.V / (self.r or 1.0)

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        F = np.asarray(F, float)
        denom = float(F @ self.n)
        out = np.full(O.shape[0], np.inf)
        if abs(denom) < 1e-12:
            return out
        lam = ((self.C - O) @ self.n) / denom
        rel = O + lam[:, None] * F - self.C
        lx = rel @ self.uhat
        lz = rel @ self.vhat
        valid = ((np.maximum(np.abs(lx), np.abs(lz)) <= 1 + 1e-6)
                 & (np.hypot(lx, lz) >= 1 - 1e-6)
                 & _angle_in_sector(lx, lz, self.sector))
        return np.where(valid, lam, out)
```

- [ ] **Step 5.3: Run** → PASS. **Commit** `feat(primitives): NdisOccluder`

---

### Task 6: ndis faces + hole-aware face plumbing (rings included)

**Files:**
- Modify: `brick_icons/shade.py` — `faces_from_analytic`, `_overlap_witness`, `order_faces` (witness call), `apply_affine_faces`
- Test: `tests/test_shade.py`

Faces may now carry `f["holes"] = [ring_px_array, ...]` (ndis full-sector, ring
full-sector). `zs` stays aligned with the OUTER ring only (planar faces — the
affine depth fit needs any 3 spread vertices).

- [ ] **Step 6.1: Failing tests**

```python
def _iso():
    return hlr.view_basis(30.0, 45.0)


def test_ndis_face_polygon_quarter():
    right, up, fwd = np.eye(3)[0], np.eye(3)[1], np.array([0.0, 0.0, -1.0])
    # ndis in the screen plane: axis toward camera
    R = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]], float).T  # U=x, A=-z? build directly:
    R = np.column_stack([np.array([1.0, 0, 0]),      # U (local x)
                         np.array([0.0, 0, 1.0]),    # A (axis) -> +z
                         np.array([0.0, 1.0, 0])])   # V (local z)
    rec = {"kind": "ndis", "sector": 90.0, "inner": 0, "R": R, "t": np.zeros(3)}
    faces = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)
    assert len(faces) == 1
    f = faces[0]
    # shoelace area of px polygon ~ 1 - pi/4 (screen-plane, unit scale)
    p = f["poly"]
    area = 0.5 * abs(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))
    assert abs(area - (1 - math.pi / 4)) < 0.01
    assert not f.get("holes")


def test_ndis_face_full_sector_has_hole():
    right, up, fwd = np.eye(3)[0], np.eye(3)[1], np.array([0.0, 0.0, -1.0])
    R = np.column_stack([np.array([1.0, 0, 0]), np.array([0.0, 0, 1.0]),
                         np.array([0.0, 1.0, 0])])
    rec = {"kind": "ndis", "sector": 360.0, "inner": 0, "R": R, "t": np.zeros(3)}
    f = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)[0]
    assert len(f["poly"]) == 4 and len(f.get("holes", [])) == 1


def test_ring_full_sector_uses_hole():
    right, up, fwd = np.eye(3)[0], np.eye(3)[1], np.array([0.0, 0.0, -1.0])
    R = np.column_stack([np.array([1.0, 0, 0]), np.array([0.0, 0, 1.0]),
                         np.array([0.0, 1.0, 0])])
    rec = {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": np.zeros(3)}
    f = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)[0]
    assert len(f.get("holes", [])) == 1
    assert len(f["zs"]) == len(f["poly"])


def test_overlap_witness_respects_holes():
    outer = np.array([(0, 0), (10, 0), (10, 10), (0, 10)], float)
    hole = np.array([(2, 2), (8, 2), (8, 8), (2, 8)], float)
    other = np.array([(4, 4), (6, 4), (6, 6), (4, 6)], float)  # entirely in hole
    assert shade._overlap_witness(outer, other, ha=(hole,)) is None


def test_apply_affine_remaps_holes():
    f = {"poly": np.array([(0, 0), (4, 0), (4, 4)], float),
         "holes": [np.array([(1, 1), (2, 1), (2, 2)], float)],
         "depth": 0.0}
    out = shade.apply_affine_faces([f], 2.0, 1.0, 1.0)[0]
    assert np.allclose(out["holes"][0][0], (3.0, 3.0))
```

Run → FAIL.

- [ ] **Step 6.2: Implement.**

(a) `_overlap_witness(pa, pb, ha=(), hb=(), grid=48)`: the inner `mask`
becomes `mask(p, holes)` — after the polygon fill, draw each hole with
`fill=0`; call sites `mask(pa, ha) & mask(pb, hb)`.

(b) In `order_faces`, the witness call becomes:

```python
            w = _overlap_witness(faces[i]["poly"], faces[j]["poly"],
                                 ha=faces[i].get("holes") or (),
                                 hb=faces[j].get("holes") or ())
```

(c) `apply_affine_faces`: after remapping `poly`, add

```python
        if face.get("holes"):
            nf["holes"] = [np.stack([h[:, 0] * f + ox, h[:, 1] * f + oy], axis=1)
                           for h in face["holes"]]
```

(d) ring branch of `faces_from_analytic` (full sector gets a real hole; the
partial-sector concat polygon stays — it is simple and valid):

```python
            if kind == "ring":
                outer = _radius_pts(rec, th, 0.0, radius=rec["inner"] + 1)
                inner = _radius_pts(rec, th, 0.0, radius=rec["inner"])
                if sect >= 2 * math.pi - 1e-6:
                    w, hole_w = outer, inner
                else:
                    w, hole_w = np.concatenate([outer, inner[::-1]], axis=0), None
            else:
                w, hole_w = _radius_pts(rec, th, 0.0), None
            px, py, z = _project_px(w, right, up, fwd, s, cx, cy, half)
            ...existing normal code...
            face = {"poly": np.stack([px, py], 1), "normal": nv,
                    "depth": float(np.mean(z)), "zs": z, "kind": kind, "rec": rec}
            if hole_w is not None:
                hx, hy, _ = _project_px(hole_w, right, up, fwd, s, cx, cy, half)
                face["holes"] = [np.stack([hx, hy], 1)]
            faces.append(face)
```

(e) ndis branch + helpers (new code in `shade.py`):

```python
def _square_pt(th):
    c, s_ = math.cos(th), math.sin(th)
    m = max(abs(c), abs(s_))
    return c / m, s_ / m


def _ndis_local_rings(sect):
    """Local 2-D (x, z) rings for square-minus-disc over [0, sect] radians.
    Returns (outer_ring, holes). Full sector: square exterior + circular hole.
    Partial: arc out, square boundary back (corners inserted — points between
    corners lie on straight square edges, so corners suffice)."""
    if sect >= 2 * math.pi - 1e-6:
        sq = np.array([(1, 1), (-1, 1), (-1, -1), (1, -1)], float)
        th = np.linspace(0.0, 2 * math.pi, 65)[:-1]
        return sq, [np.stack([np.cos(th), np.sin(th)], 1)]
    th = np.linspace(0.0, sect, 48)
    arc = np.stack([np.cos(th), np.sin(th)], 1)
    corners = [a for a in (math.radians(x) for x in (45, 135, 225, 315))
               if a < sect - 1e-9]
    back = ([_square_pt(sect)] + [_square_pt(a) for a in reversed(corners)]
            + [_square_pt(0.0)])
    return np.vstack([arc, np.array(back, float)]), []
```

In `faces_from_analytic`, add a branch (alongside disc/ring/cyli):

```python
        elif kind == "ndis":
            ring2d, holes2d = _ndis_local_rings(sect)
            U, A, V = R[:, 0], R[:, 1], R[:, 2]
            C = np.asarray(rec["t"], float)

            def world(r2):
                return C + r2[:, 0:1] * U + r2[:, 1:2] * V

            px, py, z = _project_px(world(ring2d), right, up, fwd, s, cx, cy, half)
            n = A / np.linalg.norm(A)
            nv = np.array([n @ right, n @ up, n @ fwd])
            if nv[2] > 0:
                nv = -nv
            face = {"poly": np.stack([px, py], 1), "normal": nv,
                    "depth": float(np.mean(z)), "zs": z, "kind": kind, "rec": rec}
            if holes2d:
                hx, hy, _ = _project_px(world(holes2d[0]), right, up, fwd,
                                        s, cx, cy, half)
                face["holes"] = [np.stack([hx, hy], 1)]
            faces.append(face)
```

- [ ] **Step 6.3: Run** `tests/test_shade.py` then the whole suite → PASS.
- [ ] **Step 6.4: Commit** `feat(shade): ndis analytic faces; hole-aware faces (ring bore included)`

---

### Task 7: cone wall faces + gradients

**Files:**
- Modify: `brick_icons/shade.py` — `_radius_pts`, `_wall_span_face`, new `_con_wall_faces`, dispatch in `faces_from_analytic`
- Test: `tests/test_shade.py`

- [ ] **Step 7.1: Failing tests**

```python
def _cone_rec(N=1, sector=360.0):
    return {"kind": "con", "sector": sector, "inner": N,
            "R": np.eye(3), "t": np.zeros(3)}


def test_cone_wall_faces_outer_and_interior():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic([_cone_rec()], right, up, fwd,
                                      1.0, 0.0, 0.0, 0.0)
    outer = [f for f in faces if not f.get("interior")]
    inner = [f for f in faces if f.get("interior")]
    assert len(outer) == 1 and len(inner) == 1
    assert abs(outer[0]["span_deg"] - 180.0) < 1e-6
    # cone flare: every gradient-sample normal has a positive up-component
    ups = [nv[1] for _, nv in outer[0]["grad_samples"]]
    assert all(u > 0.5 for u in ups)            # (cos,1,sin)/sqrt2 -> up = .707


def test_cone_wall_radii_taper():
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    f = [x for x in shade.faces_from_analytic([_cone_rec(N=1)], right, up, fwd,
                                              1.0, 0.0, 0.0, 0.0)
         if not x.get("interior")][0]
    xs = np.abs(f["poly"][:, 0])
    assert abs(xs.max() - 2.0) < 1e-6           # base radius N+1


def test_cone_axis_on_view_full_annulus_wall():
    # looking straight down the axis from above the apex: the whole outer wall
    # is visible as an annulus-like band (unlike a cylinder, which shows none).
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 0.0, 1.0])
    fwd = np.array([0.0, -1.0, 0.0])
    faces = shade.faces_from_analytic([_cone_rec()], right, up, fwd,
                                      1.0, 0.0, 0.0, 0.0)
    assert len(faces) == 1 and not faces[0].get("interior")


def test_cylinder_wall_faces_unchanged():
    # regression: generalizing helpers must not perturb cylinder output
    rec = {"kind": "cyli", "sector": 360.0, "inner": 0,
           "R": np.eye(3), "t": np.zeros(3)}
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_analytic([rec], right, up, fwd, 1.0, 0.0, 0.0, 0.0)
    assert {f.get("interior", False) for f in faces} == {False, True}
    for f in faces:
        assert abs(f["span_deg"] - 180.0) < 1e-6
        for _, nv in f["grad_samples"]:
            assert abs(nv[1]) < 1e-9            # cylinder normals have no up
```

Run → FAIL (cone kind unhandled; keep the cylinder test passing throughout).

- [ ] **Step 7.2: Implement.**

(a) `_radius_pts` default radius becomes kind- and level-aware:

```python
    if radius is None:
        if rec["kind"] == "ring":
            radius = rec["inner"] + 1
        elif rec["kind"] == "con":
            radius = rec["inner"] + 1 - level      # N+1 at base -> N at top
        else:
            radius = 1.0
```

(b) `_wall_span_face(...)` gains `normal_fn=None`; the per-θ normal becomes:

```python
        if normal_fn is None:
            n = math.cos(th) * U + math.sin(th) * V
        else:
            n = normal_fn(th)
        n = n / np.linalg.norm(n)
```

and the face kind comes from the rec: `"kind": rec["kind"]`.

(c) New `_con_wall_faces` (after `_cyl_wall_faces`):

```python
def _con_wall_faces(rec, R, sect, right, up, fwd, s, cx, cy, half):
    """Cone wall fills. Unlike a cylinder, the front-facing arc is NOT a half:
    n(theta).fwd = hyp*cos(theta - phi0) - C with g = R^-1 @ fwd, (A,B,C) =
    (g0, g2, -g1), so the outer wall is visible on (phi0+d, phi0+2pi-d) where
    d = acos(C/hyp) — the generator angles — and the interior far wall on its
    complement. Axis-on view (hyp ~ 0): the whole wall faces one way."""
    Minv = np.linalg.inv(R)
    g = Minv @ np.asarray(fwd, float)
    A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
    MT = Minv.T

    def normal_fn(th):
        return MT @ np.array([math.cos(th), 1.0, math.sin(th)])

    hyp = math.hypot(A_, B_)
    if hyp < 1e-12:
        spans = [(0.0, 2 * math.pi, float(g[1]) > 0)]
    elif abs(C_) >= hyp:
        # every generator faces the same way: fully front (C<=-hyp) or back
        spans = [(0.0, 2 * math.pi, C_ >= hyp)]
    else:
        phi0 = math.atan2(B_, A_)
        d = math.acos(max(-1.0, min(1.0, C_ / hyp)))
        spans = [(phi0 + d, phi0 + 2 * math.pi - d, False),
                 (phi0 - d, phi0 + d, True)]
    U, V = R[:, 0], R[:, 2]
    faces = []
    for start, end, interior in spans:
        if end - start < 1e-6:
            continue
        for lo, hi in _arc_sector_spans(start, end - start, sect):
            f = _wall_span_face(rec, U, V, lo, hi, interior, right, up, fwd,
                                s, cx, cy, half, normal_fn=normal_fn)
            if f is not None:
                faces.append(f)
    return faces
```

(d) Dispatch in `faces_from_analytic`:

```python
        elif kind == "con":
            faces.extend(_con_wall_faces(rec, R, sect, right, up, fwd,
                                         s, cx, cy, half))
```

Note the axis-on interior case (`g[1] > 0`, camera under the base looking up
through the bore): span `(0, 2π, True)` — `_arc_sector_spans` full-sector
shortcut keeps it one face.

- [ ] **Step 7.3: Run** `tests/test_shade.py` + full suite → PASS.
- [ ] **Step 7.4: Commit** `feat(shade): cone wall faces — exact generator-bounded spans + flare gradients`

---

### Task 8: wire cones/ndis into `hlr`

**Files:**
- Modify: `brick_icons/hlr.py` — `_visible_segments_analytic` occluder dispatch, `_analytic_circle_pts`
- Test: `tests/test_hlr.py` (vendor-gated, same skip pattern as existing e2e tests there)

- [ ] **Step 8.1: Failing test** (match the file's existing vendor-skip idiom)

```python
def test_cone_part_uses_analytic_cones():
    # 4589 (cone 1x1) body = 4-4con3 + 4-4con4: must arrive as analytic
    # records with cone occluders and produce cone wall fills, not tri clouds.
    res = hlr.visible_segments("4589", LDRAW)          # existing helper/const
    kinds = {r["kind"] for r in res.analytic}
    assert "con" in kinds
    assert any(f.get("kind") == "con" for f in res.faces)
    # ndis substitution reaches parts too (3960's base uses 4-4ndis)
    res2 = hlr.visible_segments("3960", LDRAW)
    assert "ndis" in {r["kind"] for r in res2.analytic}
```

Run → FAIL (`KeyError`/missing occluder or no con faces).

- [ ] **Step 8.2: Implement.**

(a) Occluder dispatch in `_visible_segments_analytic`:

```python
        if k == "cyli":
            occ = primitives.CylinderOccluder(rec["R"], rec["t"], rec["sector"])
        elif k == "con":
            occ = primitives.ConeOccluder(rec["R"], rec["t"], rec["sector"],
                                          rec["inner"])
        elif k == "disc":
            occ = primitives.DiscOccluder(rec["R"], rec["t"], rec["sector"], 0.0, 1.0)
        elif k == "ring":
            occ = primitives.DiscOccluder(rec["R"], rec["t"], rec["sector"],
                                          rec["inner"], rec["inner"] + 1)
        elif k == "ndis":
            occ = primitives.NdisOccluder(rec["R"], rec["t"], rec["sector"])
        else:
            occ = None                                  # edge: no surface
```

(b) `_analytic_circle_pts` covers the new kinds' extents:

```python
    if rec["kind"] == "cyli":
        return np.vstack([circ, circ + R[:, 1]])      # base + top rings
    if rec["kind"] == "con":
        top = C + R[:, 1] + rec["inner"] * (np.cos(ang)[:, None] * R[:, 0]
                                            + np.sin(ang)[:, None] * R[:, 2])
        base = C + (rec["inner"] + 1) * (np.cos(ang)[:, None] * R[:, 0]
                                         + np.sin(ang)[:, None] * R[:, 2])
        return np.vstack([base, top])
    if rec["kind"] == "ndis":
        sq = np.array([(1, 1), (-1, 1), (-1, -1), (1, -1)], float)
        corners = C + sq[:, 0:1] * R[:, 0] + sq[:, 1:2] * R[:, 2]
        return np.vstack([circ, corners])
    return circ
```

(note: the existing `outer`-radius `circ` computation stays above; for `con`
it computes radius `inner+1`? No — the existing code's `outer` is
`inner + 1 if ring else 1.0`; extend that line to
`outer = (rec["inner"] + 1) if rec["kind"] in ("ring", "con") else 1.0`
so `circ` is the cone base; then the `con` branch above only needs `top`.)

- [ ] **Step 8.3: Run** vendor-gated tests + full suite → PASS.
- [ ] **Step 8.4: Commit** `feat(hlr): wire cone/ndis occluders + fit extents`

---

### Task 9: stamp facet-group ids

**Files:**
- Modify: `brick_icons/shade.py` — `_attach_smooth_gradients`
- Test: `tests/test_shade.py`

- [ ] **Step 9.1: Failing test**

```python
def test_group_ids_stamped_on_all_tri_faces():
    # two coplanar tris sharing an edge + one lone off-plane tri
    tris = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],
        [[5, 0, 1], [6, 0, 2], [5, 1, 3]],
    ], float)
    right, up = np.array([1.0, 0, 0]), np.array([0.0, 1.0, 0])
    fwd = np.array([0.0, 0.0, -1.0])
    faces = shade.faces_from_tris(tris, right, up, fwd, 1.0, 0.0, 0.0, 0.0,
                                  cond_edges=np.zeros((0, 4, 3)))
    assert all("group" in f for f in faces)
    kept = {f["group"] for f in faces}
    coplanar = [f for f in faces if abs(f["normal"][2]) > 0.99]
    assert len({f["group"] for f in coplanar}) == 1     # merged into one group
    assert len(kept) == 2
```

(If the lone tri is back-facing under this view, flip its winding in the test
data until three faces survive — assert `len(faces) == 3` first.)
Run → FAIL (`group` missing).

- [ ] **Step 9.2: Implement.** In `_attach_smooth_gradients`, after the
union-find loop (before the `groups` gradient logic), stamp every face:

```python
    for k in range(len(faces)):
        faces[k]["group"] = find(k)
```

Also update `faces_from_tris` so the cond-edge gate doesn't skip stamping when
there are no conditional edges:

```python
    if cond_edges is not None and len(cond_edges):
        _attach_smooth_gradients(faces, cond_edges)
    else:
        _attach_smooth_gradients(faces, np.zeros((0, 2, 3)))
```

(`_seam_edge_mask` with zero cond edges yields no seams; coplanar unions still
form, which is what flat-surface merging needs.)

- [ ] **Step 9.3: Run** full suite → PASS. **Commit** `feat(shade): stamp facet-group ids (smooth + coplanar)`

---

### Task 10: fragment clipping + group merge in `fill_ops`; evenodd fills

**Files:**
- Modify: `brick_icons/shade.py` — rewrite `fill_ops`, delete `_poly_d`
- Modify: `brick_icons/trace.py:125` — fill path element gains `fill-rule="evenodd"`
- Test: `tests/test_shade.py`, `tests/test_trace.py`

- [ ] **Step 10.1: Failing tests**

```python
def _flat_face(x0, y0, x1, y1, order, depth, normal=(0, 1, 0), group=None):
    f = {"poly": np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float),
         "normal": np.array(normal, float), "depth": float(depth),
         "order": order, "kind": "tri"}
    if group is not None:
        f["group"] = group
    return f


def test_fill_ops_drops_fully_hidden_face():
    far = _flat_face(2, 2, 8, 8, order=0, depth=10.0)
    near = _flat_face(0, 0, 10, 10, order=1, depth=1.0)
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 1


def test_fill_ops_clips_partial_overlap():
    far = _flat_face(0, 0, 10, 10, order=0, depth=10.0, normal=(-1, 0, 0))
    near = _flat_face(5, 0, 15, 10, order=1, depth=1.0)
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 2
    # far op's fragment must not extend past x=5: no coordinate > 5 in its d
    far_op = [o for o in ops if o["fill"] != ops[-1]["fill"] or True][0]  # first = farthest
    xs = [float(tok) for tok in far_op["d"].replace("M", " ").replace("L", " ")
          .replace("Z", " ").split()][0::2]
    assert max(xs) <= 5.0 + 1e-6


def test_fill_ops_merges_group_into_one_op():
    kw = dict(depth=5.0, normal=(0, 1, 0), group=7)
    fs = [_flat_face(0, 0, 4, 4, order=0, **kw),
          _flat_face(4, 0, 8, 4, order=1, **kw),
          _flat_face(0, 4, 8, 8, order=2, **kw)]   # T-junction against the first two
    ops = shade.fill_ops(fs, shade.Flat3Style())
    assert len(ops) == 1
    assert ops[0]["d"].count("M ") == 1            # a single merged region


def test_fill_ops_group_gradient_kept():
    ga = ((0.0, 0.0), (8.0, 0.0))
    samples = [(0.0, np.array([0, 0, -1.0])), (1.0, np.array([0.6, 0, -0.8]))]
    fs = []
    for i, (x0, x1) in enumerate([(0, 4), (4, 8)]):
        f = _flat_face(x0, 0, x1, 4, order=i, depth=5.0, group=3)
        f["grad_axis"] = ga
        f["grad_samples"] = samples
        fs.append(f)
    ops = shade.fill_ops(fs, shade.Flat3Style())
    assert len(ops) == 1 and "gradient" in ops[0]


def test_fill_ops_tiny_slivers_dropped():
    far = _flat_face(0, 0, 10, 10, order=0, depth=10.0)
    near = _flat_face(0.01, 0.01, 10, 10, order=1, depth=1.0)   # covers all but a sliver
    ops = shade.fill_ops([far, near], shade.Flat3Style())
    assert len(ops) == 1
```

And in `tests/test_trace.py`:

```python
def test_fill_paths_use_evenodd():
    segs = []
    fills = [{"d": "M 0 0 L 10 0 L 10 10 L 0 10 Z M 2 2 L 8 2 L 8 8 L 2 8 Z",
              "fill": "#888888", "depth": 0.0}]
    out = trace.segments_to_svg(segs, 20, 20, tmp_path / "f.svg", fills=fills)
    txt = out.read_text()
    assert 'fill-rule="evenodd"' in txt
```

(adapt to that file's existing tmp_path fixture usage). Run → FAIL.

- [ ] **Step 10.2: Implement.** Replace `_poly_d` + `fill_ops` in `shade.py`
(new import `from . import geom2d` at top):

```python
MIN_FRAG_AREA = 0.2     # px^2: visible fragments smaller than this are noise


def fill_ops(faces, style):
    """Fill ops with exact visible-fragment clipping and per-surface merging.

    1) paint order: witness order when stamped, else far->near mean depth;
    2) CLIP nearest-first: each face's fragment = its polygon minus the union
       of everything nearer — the SVG contains zero hidden geometry;
    3) MERGE fragments sharing a facet-group id (smooth or coplanar groups
       share one gradient/tone by construction) via polygon union — one
       element per visually continuous surface. Union is robust to the
       T-junction tessellations and projected self-overlap that killed
       boundary tracing (see 2026-07-05 spec).
    Emitted farthest-first (fragments are disjoint, so order only affects
    which anti-alias stroke wins along shared boundaries)."""
    if faces and all("order" in f for f in faces):
        ordered = sorted(faces, key=lambda f: f["order"])
    else:
        ordered = sorted(faces, key=lambda f: -f["depth"])
    frags = {}
    cover = None
    for idx in range(len(ordered) - 1, -1, -1):
        f = ordered[idx]
        g = geom2d.to_geom(f["poly"], f.get("holes"))
        if g.is_empty:
            continue
        frag = g if cover is None else geom2d.difference(g, cover)
        if geom2d.area(frag) >= MIN_FRAG_AREA:
            frags[idx] = frag
        cover = g if cover is None else geom2d.union(cover, g)

    members = defaultdict(list)                 # group key -> surviving indices
    for idx in frags:
        f = ordered[idx]
        key = f.get("group")
        members[("g", key) if key is not None else ("i", idx)].append(idx)

    ops, emitted = [], set()
    for idx in range(len(ordered)):
        if idx not in frags or idx in emitted:
            continue
        f = ordered[idx]
        key = f.get("group")
        ks = members[("g", key) if key is not None else ("i", idx)]
        emitted.update(ks)
        geom = frags[ks[0]] if len(ks) == 1 else \
            geom2d.union_all([frags[j] for j in ks])
        d = geom2d.path_d(geom)
        if not d:
            continue
        if "grad_axis" in f:
            p0, p1 = f["grad_axis"]
            stops = sorted(((off, style.ramp(nv)) for off, nv in f["grad_samples"]),
                           key=lambda t: t[0])
            ops.append({"d": d, "depth": f["depth"],
                        "gradient": {"x1": p0[0], "y1": p0[1],
                                     "x2": p1[0], "y2": p1[1], "stops": stops}})
        else:
            ops.append({"d": d, "fill": style.tone(f["normal"]),
                        "depth": f["depth"]})
    return ops
```

In `trace.py`, the fill path line becomes:

```python
            body.append(f'<path d="{fo["d"]}" fill="{paint}" fill-rule="evenodd" '
                        f'stroke="{paint}" stroke-width="0.8"/>')
```

- [ ] **Step 10.3: Run full suite.** Some existing `fill_ops` tests may assert
`_poly_d`-format strings or op counts that included hidden faces — update those
expectations to the clipped/merged behavior (they should assert *visible*
results now, e.g. hidden-face ops gone, `fill-rule` present). Anything that
imports `_poly_d` switches to `geom2d.path_d(geom2d.to_geom(poly))`.
- [ ] **Step 10.4: Commit** `feat(shade): visible-fragment clipping + per-surface union merge in fill_ops`

---

### Task 11: integration validation + element-count report

**Files:**
- Test: `tests/test_shade.py` or `tests/test_hlr.py` (vendor-gated)
- No new source files; fixes only if this surfaces bugs.

- [ ] **Step 11.1: Vendor-gated integration tests**

```python
def test_dish_top_is_one_gradient_path():
    # 3960's dish: hundreds of facets must merge to a handful of fill ops.
    res = hlr.visible_segments("3960", LDRAW)
    style = shade.Flat3Style()
    ops = shade.fill_ops(res.faces, style)
    grads = [o for o in ops if "gradient" in o]
    assert 0 < len(grads) < 25                  # was one per facet (hundreds)
    assert len(ops) < 80


def test_fragments_are_disjoint_no_hidden_fills():
    from brick_icons import geom2d
    res = hlr.visible_segments("3005", LDRAW)   # 1x1 brick: studs over top face
    ops = shade.fill_ops(res.faces, shade.Flat3Style())
    # re-parse the d strings: total area == area of the union (no overdraw)
    import re as _re
    def geoms(op):
        rings = []
        for sub in op["d"].split("M ")[1:]:
            pts = _re.findall(r"(-?\d+\.?\d*) (-?\d+\.?\d*)", sub)
            rings.append(np.array(pts, float))
        g = geom2d.to_geom(rings[0], holes=rings[1:])
        return g
    gs = [geoms(o) for o in ops]
    total = sum(geom2d.area(g) for g in gs)
    assert abs(total - geom2d.area(geom2d.union_all(gs))) < 1.0
```

- [ ] **Step 11.2: Run + fix.** `.venv/bin/python -m pytest -q` → all PASS.
- [ ] **Step 11.3: Manual validation renders** (per the always-show-renderings
memory — `open` the results):

```bash
.venv/bin/brick-icons --list specimens.txt --out out/frag --shading outline \
  --format both --mode gray --shade-style flat3
for f in 3960 4589 50950 3941 3001 4019 3649; do
  echo "$f: $(grep -c '<path' out/frag/$f.svg) paths"; done
qlmanage -p out/frag/3960.svg 2>/dev/null || open out/frag/3960.svg
```

Compare against a pre-change render of the same list (checkout HEAD~N to
`out/before` first if needed). Expect: dish = smooth single surface; cone 4589
exact; element counts down ~10x on curved parts; no visual regressions on the
gray masters. Time the 3649 render (`time ...`) — if fill_ops dominates and
exceeds a few seconds, batch the cover union (union chunks of 64 before
differencing).

- [ ] **Step 11.4: Commit** `test: integration guards for fragment clipping + merged surfaces`

---

## Self-Review Notes

- Spec §1 → Tasks 2–4; §2 → Tasks 2, 5, 6; §3 → Task 7 (+8 wiring); §4 →
  Tasks 9–10; §5 (error handling/perf) → geom2d fallbacks (Task 1) + 11.3
  timing check. Element-count validation → Task 11.
- Types consistent: `parse_primitive` third element doubles as ring-inner /
  cone-top (documented in Task 2); `ConeOccluder(R, t, sector, top)` matches
  Task 8 wiring; face dicts gain optional `holes` (Task 6) consumed by
  `to_geom` in Task 10 and the witness/affine plumbing in Task 6.
- Known judgment calls an executor should preserve: do NOT touch
  `CylinderOccluder` or `order_faces` internals (memory: regression-prone);
  cylinder wall output must stay byte-identical (Task 7 regression test).
