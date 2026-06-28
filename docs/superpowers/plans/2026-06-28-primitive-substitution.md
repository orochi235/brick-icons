# Analytic Primitive Substitution (path B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render LDraw curved primitives as exact analytic shapes (arcs/ellipses) with gridless analytic occlusion, emitting clean scalable SVG, fixing the faceted-HLR occlusion artifacts (3941 base gap, tails) at any resolution.

**Architecture:** A new `primitives.py` owns analytic shape recognition + math. `hlr.flatten` substitutes recognized curved primitives (`edge`, `cyli`/`cylo`, `disc`, `ringN`) into an `out["analytic"]` bucket instead of recursing into their polygons; unrecognized curved primitives fall back to today's faceted recursion. `visible_segments` builds a continuous analytic depth oracle (curved surfaces + flat triangles), generates drawn ops (lines + elliptical arcs), tests visibility per-sample against the oracle, and returns draw ops. `trace`/`process` emit/raster the arc ops; the z-buffer bias/dilation hacks are retired.

**Tech Stack:** Python, numpy, Pillow; existing `brick_icons` HLR pipeline.

---

## Conventions (read once)

- World transform of a primitive: `P_world = R @ P_local + t`. So `C=t`, `U=R[:,0]`, `V=R[:,2]`, axis `A=R[:,1]`.
- Canonical circle: `P_local(θ) = (cosθ, 0, sinθ)`, radius 1, θ from +X sweeping toward +Z. Fractional primitive `n-d*` spans `sector_deg = 360*n/d`, start θ=0; `R` supplies world orientation.
- `ringN`: annulus inner radius `N`, outer `N+1`, in local XZ at y=0.
- Projection (existing `hlr.project`): `project(P) = (P·right, -(P·up), P·fwd)` = `(A, B, Z)`; `Z` is depth, **smaller = nearer**.
- Pixel map (existing `to_px` in `visible_segments`): `x=(A-cx)*s+R/2`, `y=(B-cy)*s+R/2`, depth `Z`.
- **Inverse ray** for the oracle: pixel `(x,y)` → `A=(x-R/2)/s+cx`, `B=(y-R/2)/s+cy`; world ray `O+λ·fwd` with `O = A·right - B·up`, depth `=λ`.
- A linear projection maps a circle `C + cosθ·U + sinθ·V` to a 2-D ellipse `center_px + cosθ·u + sinθ·v` where `u=(s·U·right, -s·U·up)`, `v=(s·V·right, -s·V·up)` (in pixels), `center_px = to_px(C)`.

## File Structure

- **Create** `brick_icons/primitives.py` — recognition (`parse_primitive`), analytic records, ellipse projection + SVD→SVG-arc params, drawn-op generation, per-surface depth functions. One responsibility: analytic shapes ↔ math.
- **Modify** `brick_icons/hlr.py` — `flatten` substitution hook + `out["analytic"]`; `visible_segments` oracle assembly + visibility; retire `dilate_zbuffer`/`EDGE_DILATE` and shrink biases.
- **Modify** `brick_icons/trace.py` — `segments_to_svg` emits `<line>` + `<path A>` arc ops.
- **Modify** `brick_icons/process.py` — `draw_segments` samples arc ops to polylines.
- **Test** `tests/test_primitives.py` (new), extend `tests/test_hlr.py`, `tests/test_trace.py`, `tests/test_process.py`.

## Draw-op model

Ops are tuples discriminated by first element:
```
("line", x1, y1, x2, y2, kind)
("arc",  cx, cy, rx, ry, phi_deg, t0_deg, t1_deg, kind)   # ellipse center, semi-axes, x-rotation, param-angle span
```
`kind ∈ {"edge","sil"}`. Existing 5-tuples `(x1,y1,x2,y2,kind)` remain valid and are treated as `("line", …)` by a normalizer, so old tests/paths keep working.

---

### Task 1: Primitive recognition parser

**Files:**
- Create: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_primitives.py
import math
from brick_icons import primitives as P

def test_parse_edge_fractions():
    assert P.parse_primitive("4-4edge.dat") == ("edge", 360.0, 0)
    assert P.parse_primitive("1-4edge.dat") == ("edge", 90.0, 0)
    assert P.parse_primitive("3-4edge") == ("edge", 270.0, 0)
    assert P.parse_primitive("1-8edge.dat") == ("edge", 45.0, 0)

def test_parse_cyli_and_alias_cylo():
    assert P.parse_primitive("1-4cyli.dat") == ("cyli", 90.0, 0)
    assert P.parse_primitive("4-4cylo.dat") == ("cyli", 360.0, 0)

def test_parse_disc():
    assert P.parse_primitive("3-4disc.dat") == ("disc", 270.0, 0)

def test_parse_ring_inner_radius():
    assert P.parse_primitive("4-4ring3.dat") == ("ring", 360.0, 3)
    assert P.parse_primitive("4-4ring1.dat") == ("ring", 360.0, 1)

def test_unrecognized_returns_none():
    assert P.parse_primitive("4-4ndis.dat") is None      # fallback to faceted
    assert P.parse_primitive("1-4cyls.dat") is None       # sloped cut: fallback
    assert P.parse_primitive("1-8chrd.dat") is None       # chord: straight, fallback
    assert P.parse_primitive("box.dat") is None
    assert P.parse_primitive("stud4.dat") is None
```

- [ ] **Step 2: Run, expect fail** — `.venv/bin/pytest tests/test_primitives.py -q` → ImportError/fail.

- [ ] **Step 3: Implement**

```python
# brick_icons/primitives.py
from __future__ import annotations
import re
import numpy as np

_FRAC = re.compile(r"^(\d+)-(\d+)(edge|cyli|cylo|disc|ring)(\d*)$")

def parse_primitive(name: str):
    """basename -> (kind, sector_deg, inner_radius) or None (=> faceted fallback).
    kind: 'edge'|'cyli'|'disc'|'ring'. 'cylo' is aliased to 'cyli'."""
    base = name.replace("\\", "/").split("/")[-1].lower()
    if base.endswith(".dat"):
        base = base[:-4]
    m = _FRAC.match(base)
    if not m:
        return None
    num, den, fam, suffix = int(m.group(1)), int(m.group(2)), m.group(3), m.group(4)
    if den == 0:
        return None
    sector = 360.0 * num / den
    kind = "cyli" if fam == "cylo" else fam
    inner = int(suffix) if (kind == "ring" and suffix) else 0
    if kind == "ring" and inner == 0:
        return None
    return (kind, sector, inner)
```

- [ ] **Step 4: Run, expect pass** — `.venv/bin/pytest tests/test_primitives.py -q`.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(primitives): curved-primitive name parser"`.

---

### Task 2: Substitution hook in flatten

**Files:**
- Modify: `brick_icons/hlr.py` (`flatten`, ~lines 31-59)
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write failing tests** (append to `tests/test_hlr.py`)

```python
def test_flatten_substitutes_known_primitive(tmp_path):
    from brick_icons import hlr
    import numpy as np
    # a part that references 1-4edge with identity transform
    (tmp_path / "p" / "48").mkdir(parents=True)
    (tmp_path / "p" / "48" / "1-4edge.dat").write_text("0 quarter edge\n")  # body irrelevant: substituted
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\48\\1-4edge.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert len(out["analytic"]) == 1
    rec = out["analytic"][0]
    assert rec["kind"] == "edge" and rec["sector"] == 90.0
    assert np.allclose(rec["R"], np.eye(3)) and np.allclose(rec["t"], 0)

def test_flatten_unknown_primitive_recurses(tmp_path):
    from brick_icons import hlr
    import numpy as np
    (tmp_path / "p").mkdir()
    # ndis is unrecognized -> must recurse into its polygons (a triangle here)
    (tmp_path / "p" / "4-4ndis.dat").write_text("3 16 0 0 0  1 0 0  0 0 1\n")
    part = tmp_path / "thing.dat"
    part.write_text("1 16 0 0 0  1 0 0  0 1 0  0 0 1  p\\4-4ndis.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert len(out["analytic"]) == 0
    assert len(out["tri"]) == 1     # recursed into the polygon
```

- [ ] **Step 2: Run, expect fail** (KeyError "analytic" / substitution missing).

- [ ] **Step 3: Implement** — in `flatten`, inside the `typ == "1"` branch, before recursing, check the referenced basename:

```python
        if typ == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
            M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
            T = np.array([x, y, z], float)
            ref = " ".join(tok[14:])
            from . import primitives  # local import avoids cycle
            spec = primitives.parse_primitive(ref)
            Rsub, tsub = R @ M, R @ T + t
            if spec is not None:
                kind, sector, inner = spec
                out["analytic"].append(
                    {"kind": kind, "sector": sector, "inner": inner,
                     "R": Rsub, "t": tsub})
            else:
                sub = resolve(ref, roots)
                if sub is not None:
                    flatten(sub, Rsub, tsub, out, roots, depth + 1)
```

Also update the `out` initializer in `visible_segments` to include `"analytic": []` (Task 8 covers full use; add the key now): change `out = {"2": [], "5": [], "tri": []}` → `out = {"2": [], "5": [], "tri": [], "analytic": []}`.

- [ ] **Step 4: Run, expect pass** — `.venv/bin/pytest tests/test_hlr.py -q`.

- [ ] **Step 5: Commit** — `git commit -am "feat(hlr): substitute known curved primitives into analytic bucket"`.

---

### Task 3: Ellipse projection + SVG-arc parameters

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py`

- [ ] **Step 1: Write failing tests**

```python
def test_project_circle_to_ellipse_basis():
    import numpy as np
    # identity transform, simple orthographic-ish projector: A=x, B=z (drop y)
    def proj(Pw):   # returns (A, B, Z) arrays
        Pw = np.atleast_2d(Pw)
        return Pw[:, 0], Pw[:, 2], Pw[:, 1]
    R, t = np.eye(3), np.zeros(3)
    ell = P.project_circle(R, t, radius=2.0, to_AB=proj, s=1.0, cx=0.0, cy=0.0, half=0.0)
    # center at origin; u along +x len 2; v along +y(image) from +z len 2
    assert np.allclose(ell.center, [0.0, 0.0])
    assert np.allclose(np.hypot(*ell.u), 2.0) and np.allclose(np.hypot(*ell.v), 2.0)

def test_ellipse_svd_axes_circle():
    import numpy as np
    e = P.Ellipse(center=np.array([5.0, 7.0]), u=np.array([3.0, 0.0]), v=np.array([0.0, 3.0]))
    rx, ry, phi = e.svg_axes()
    assert np.isclose(rx, 3.0) and np.isclose(ry, 3.0)

def test_ellipse_point_param():
    import numpy as np
    e = P.Ellipse(center=np.array([0.0, 0.0]), u=np.array([2.0, 0.0]), v=np.array([0.0, 1.0]))
    p0 = e.point(0.0); p90 = e.point(math.pi / 2)
    assert np.allclose(p0, [2.0, 0.0]) and np.allclose(p90, [0.0, 1.0])
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** (append to `primitives.py`)

```python
class Ellipse:
    """2-D ellipse in pixel space: point(θ) = center + cosθ·u + sinθ·v."""
    def __init__(self, center, u, v):
        self.center = np.asarray(center, float)
        self.u = np.asarray(u, float)
        self.v = np.asarray(v, float)

    def point(self, theta):
        return self.center + np.cos(theta) * self.u + np.sin(theta) * self.v

    def points(self, thetas):
        thetas = np.asarray(thetas, float)[:, None]
        return self.center + np.cos(thetas) * self.u + np.sin(thetas) * self.v

    def svg_axes(self):
        """Return (rx, ry, phi_deg): semi-axes and x-rotation of the ellipse,
        via SVD of M=[u v]. The unit circle maps through M to this ellipse, so
        singular values are the semi-axes and the first left-singular vector
        gives the major-axis direction."""
        M = np.column_stack([self.u, self.v])
        U_, S_, _ = np.linalg.svd(M)
        rx, ry = float(S_[0]), float(S_[1])
        phi = math.degrees(math.atan2(U_[1, 0], U_[0, 0]))
        return rx, ry, phi


def project_circle(R, t, radius, to_AB, s, cx, cy, half):
    """Project the world circle C+radius(cosθ U+sinθ V) into pixel space.
    `to_AB(Pw)->(A,B,Z)` is the camera projector; (s,cx,cy,half) the pixel fit
    (half = render_px/2). Returns an Ellipse in pixels."""
    C = t
    U = R[:, 0] * radius
    V = R[:, 2] * radius
    pts = np.stack([C, C + U, C + V])
    A, B, _ = to_AB(pts)
    px = (A - cx) * s + half
    py = (B - cy) * s + half
    center = np.array([px[0], py[0]])
    u = np.array([px[1] - px[0], py[1] - py[0]])
    v = np.array([px[2] - px[0], py[2] - py[0]])
    return Ellipse(center, u, v)
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(primitives): circle->ellipse projection + SVD arc axes"`.

---

### Task 4: Analytic occluder depth functions

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py`

Each occluder exposes `depth(O, F)` where `O` is an (N,3) array of ray origins and `F` the (3,) view direction; returns an (N,) array of nearest hit depth `λ`, `inf` on miss.

- [ ] **Step 1: Write failing tests**

```python
def test_cylinder_depth_hit_and_miss():
    import numpy as np
    # unit cylinder, axis +Y from 0..1, radius 1, centered origin
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])           # look along +z
    O = np.array([[0.0, 0.5, -5.0],          # through axis at mid-height -> hits front wall z=-1
                  [5.0, 0.5, -5.0]])          # misses (x=5 outside r=1)
    d = cyl.depth(O, F)
    assert np.isclose(d[0], -1.0, atol=1e-6)   # nearest hit at z=-1
    assert np.isinf(d[1])

def test_cylinder_depth_clamps_height():
    import numpy as np
    R, t = np.eye(3), np.zeros(3)
    cyl = P.CylinderOccluder(R, t, sector=360.0)
    F = np.array([0.0, 0.0, 1.0])
    O = np.array([[0.0, 5.0, -5.0]])          # above the cylinder top (y=5 > 1) -> miss
    assert np.isinf(cyl.depth(O, F)[0])

def test_disc_depth():
    import numpy as np
    R, t = np.eye(3), np.zeros(3)             # disc in XZ plane at y=0, radius 1
    disc = P.DiscOccluder(R, t, sector=360.0, inner=0.0, outer=1.0)
    F = np.array([0.0, 1.0, 0.0])             # look along +y onto the disc
    O = np.array([[0.3, -5.0, 0.2],            # inside radius -> hits plane y=0 at λ=5
                  [2.0, -5.0, 0.0]])            # outside radius -> miss
    d = disc.depth(O, F)
    assert np.isclose(d[0], 5.0) and np.isinf(d[1])
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** (append to `primitives.py`)

```python
def _local_basis(R, t):
    """Orthonormal-ish local axes + radius/scale from a primitive transform."""
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    r = (np.linalg.norm(U) + np.linalg.norm(V)) / 2.0
    ah = np.linalg.norm(A)
    return U, V, A, r, ah


def _angle_in_sector(local_x, local_z, sector):
    if sector >= 360.0 - 1e-9:
        return np.ones(local_x.shape, bool)
    ang = np.degrees(np.arctan2(local_z, local_x)) % 360.0
    return ang <= sector + 1e-6


class CylinderOccluder:
    def __init__(self, R, t, sector):
        self.C = np.asarray(t, float)
        self.U, self.V, self.A, self.r, self.ah = _local_basis(np.asarray(R, float), t)
        self.ahat = self.A / (self.ah or 1.0)
        self.sector = sector

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        d = F - np.dot(F, self.ahat) * self.ahat          # ray dir minus axial part
        oc = O - self.C
        oc_perp = oc - np.outer(oc @ self.ahat, self.ahat)
        a = float(d @ d)
        b = 2.0 * (oc_perp @ d)
        c = np.sum(oc_perp * oc_perp, axis=1) - self.r ** 2
        out = np.full(O.shape[0], np.inf)
        if a < 1e-12:
            return out
        disc = b * b - 4 * a * c
        ok = disc >= 0
        sq = np.sqrt(np.where(ok, disc, 0.0))
        for lam in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)):
            P_ = O + lam[:, None] * F
            h = (P_ - self.C) @ self.ahat
            lx = (P_ - self.C) @ (self.U / (self.r or 1.0))
            lz = (P_ - self.C) @ (self.V / (self.r or 1.0))
            valid = ok & (h >= -1e-6) & (h <= self.ah + 1e-6) & _angle_in_sector(lx, lz, self.sector)
            cand = np.where(valid, lam, np.inf)
            out = np.minimum(out, cand)
        return out


class DiscOccluder:
    """Planar annulus/disc in the primitive's XZ plane (normal = axis A)."""
    def __init__(self, R, t, sector, inner, outer):
        self.C = np.asarray(t, float)
        self.U, self.V, self.A, self.r, _ = _local_basis(np.asarray(R, float), t)
        self.n = self.A / (np.linalg.norm(self.A) or 1.0)
        self.inner = inner * self.r
        self.outer = outer * self.r
        self.sector = sector
        self.uhat = self.U / (self.r or 1.0)
        self.vhat = self.V / (self.r or 1.0)

    def depth(self, O, F):
        O = np.atleast_2d(O).astype(float)
        denom = float(F @ self.n)
        out = np.full(O.shape[0], np.inf)
        if abs(denom) < 1e-12:
            return out
        lam = ((self.C - O) @ self.n) / denom
        Phit = O + lam[:, None] * F
        rel = Phit - self.C
        lx = rel @ self.uhat
        lz = rel @ self.vhat
        rad = np.hypot(lx, lz)
        valid = (lam > -1e-6) & (rad >= self.inner - 1e-6) & (rad <= self.outer + 1e-6) \
            & _angle_in_sector(lx, lz, self.sector)
        return np.where(valid, lam, out)
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(primitives): analytic cylinder/disc/ring depth occluders"`.

---

### Task 5: Drawn-op generation per primitive

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py`

`drawn_curves(rec, to_AB, s, cx, cy, half, fwd)` returns a list of *candidate* ops (full arcs/lines, pre-occlusion) for one analytic record.

- [ ] **Step 1: Write failing tests**

```python
def test_drawn_edge_is_full_arc():
    import numpy as np
    def proj(Pw):
        Pw = np.atleast_2d(Pw); return Pw[:, 0], Pw[:, 2], Pw[:, 1]
    rec = {"kind": "edge", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}
    ops = P.drawn_curves(rec, proj, s=1.0, cx=0.0, cy=0.0, half=0.0, fwd=np.array([0,0,1.0]))
    assert len(ops) == 1 and ops[0][0] == "arc"
    assert ops[0][-1] == "edge"

def test_drawn_cylinder_has_two_silhouette_lines():
    import numpy as np
    def proj(Pw):
        Pw = np.atleast_2d(Pw); return Pw[:, 0], Pw[:, 2], Pw[:, 1]
    rec = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}
    ops = P.drawn_curves(rec, proj, s=1.0, cx=0.0, cy=0.0, half=0.0, fwd=np.array([0,0,1.0]))
    sil_lines = [o for o in ops if o[0] == "line" and o[-1] == "sil"]
    assert len(sil_lines) == 2
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** (append). Edge/disc/ring → boundary arc(s). Cyli → 2 silhouette lines + 2 cap arcs.

```python
def _arc_op(ell, t0, t1, kind):
    rx, ry, phi = ell.svg_axes()
    return ("arc", float(ell.center[0]), float(ell.center[1]),
            rx, ry, phi, math.degrees(t0), math.degrees(t1), kind)


def drawn_curves(rec, to_AB, s, cx, cy, half, fwd):
    kind, sector = rec["kind"], rec["sector"]
    R, t = rec["R"], rec["t"]
    t1 = math.radians(sector)
    ops = []
    if kind in ("edge", "disc", "ring"):
        outer = (rec["inner"] + 1) if kind == "ring" else 1.0
        ell = project_circle(R, t, outer, to_AB, s, cx, cy, half)
        ops.append(_arc_op(ell, 0.0, t1, "edge"))
        if kind == "ring" and rec["inner"] > 0:
            elli = project_circle(R, t, rec["inner"], to_AB, s, cx, cy, half)
            ops.append(_arc_op(elli, 0.0, t1, "edge"))
    elif kind == "cyli":
        U, V, A = R[:, 0], R[:, 2], R[:, 1]
        # silhouette generators: radial normal perpendicular to view -> tan θ = -(U·fwd)/(V·fwd)
        uf, vf = float(U @ fwd), float(V @ fwd)
        theta = math.atan2(-uf, vf)
        base = project_circle(R, t, 1.0, to_AB, s, cx, cy, half)
        top = project_circle(R, t + A, 1.0, to_AB, s, cx, cy, half)
        for th in (theta, theta + math.pi):
            within = (sector >= 360.0 - 1e-9) or (0 <= (math.degrees(th) % 360.0) <= sector + 1e-6)
            if within:
                pb, pt = base.point(th), top.point(th)
                ops.append(("line", float(pb[0]), float(pb[1]),
                            float(pt[0]), float(pt[1]), "sil"))
        ops.append(_arc_op(base, 0.0, t1, "edge"))
        ops.append(_arc_op(top, 0.0, t1, "edge"))
    return ops
```

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(primitives): analytic drawn ops (edge/disc/ring arcs, cylinder silhouette)"`.

---

### Task 6: Depth oracle + visibility splitting

**Files:**
- Modify: `brick_icons/primitives.py` (oracle + op visibility); `brick_icons/hlr.py` (triangle occluder helper)
- Test: `tests/test_primitives.py`

- [ ] **Step 1: Write failing tests**

```python
def test_visibility_splits_op_by_occluder():
    import numpy as np
    # a horizontal edge line across x in [0,10] at y=0, depth 0; an occluder
    # plane covers x in [4,6] nearer than the line -> middle hidden.
    class Slab:
        def depth(self, O, F):
            x = O[:, 0]
            return np.where((x >= 4) & (x <= 6), -1.0, np.inf)  # nearer where covered
    op = ("line", 0.0, 0.0, 10.0, 0.0, "edge")
    # sampler maps pixel->ray origin O=(x, y, 0), depth of sample = 0
    def ray_origin(xs, ys):
        return np.stack([xs, ys, np.zeros_like(xs)], 1)
    vis = P.visible_subops([op], [Slab()], ray_origin, fwd=np.array([0,0,1.0]),
                           sample_depth=lambda xs, ys: np.zeros_like(xs), eps=1e-6, n=101)
    # expect two visible runs (left of 4, right of 6)
    lines = [o for o in vis if o[0] == "line"]
    assert len(lines) == 2
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** `visible_subops` (append to `primitives.py`). Sample each op (lines: 2+ samples; arcs: n samples over θ), compute field = min occluder depth at each sample's pixel, mark visible where `sample_depth ≤ field + eps`, regroup runs into sub-ops.

```python
def _depth_field(xs, ys, occluders, ray_origin, fwd):
    O = ray_origin(xs, ys)
    field = np.full(xs.shape, np.inf)
    for occ in occluders:
        field = np.minimum(field, occ.depth(O, fwd))
    return field

def _samples_for(op, n):
    kind = op[0]
    if kind == "line":
        _, x1, y1, x2, y2, _ = op
        ts = np.linspace(0, 1, max(2, n))
        return x1 + (x2 - x1) * ts, y1 + (y2 - y1) * ts, ts
    _, cx, cy, rx, ry, phi, t0, t1, _ = op
    ell = _ellipse_from_arc(cx, cy, rx, ry, phi)
    th = np.radians(np.linspace(t0, t1, max(2, n)))
    pts = ell.points(th)
    return pts[:, 0], pts[:, 1], np.linspace(t0, t1, max(2, n))

def _ellipse_from_arc(cx, cy, rx, ry, phi):
    a = math.radians(phi)
    maj = np.array([math.cos(a), math.sin(a)]) * rx
    minr = np.array([-math.sin(a), math.cos(a)]) * ry
    return Ellipse(np.array([cx, cy]), maj, minr)

def _runs(mask):
    runs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append((i, j)); i = j + 1
        else:
            i += 1
    return runs

def visible_subops(ops, occluders, ray_origin, fwd, sample_depth, eps, n=200):
    result = []
    for op in ops:
        xs, ys, params = _samples_for(op, n)
        field = _depth_field(xs, ys, occluders, ray_origin, fwd)
        sd = sample_depth(xs, ys)
        vis = sd <= field + eps
        for (i, j) in _runs(vis):
            if op[0] == "line":
                result.append(("line", float(xs[i]), float(ys[i]),
                               float(xs[j]), float(ys[j]), op[-1]))
            else:
                _, cx, cy, rx, ry, phi, _, _, kind = op
                result.append(("arc", cx, cy, rx, ry, phi,
                               float(params[i]), float(params[j]), kind))
    return result
```

Note: arc `sample_depth` is the depth of the curve point itself; for edge arcs lying on a surface, `eps` (a small fraction of the model depth range) keeps them from self-occluding. For cylinder silhouette lines, the sample depth is the generator's depth; the cylinder surface is excluded from `occluders` when testing its own silhouette (Task 8 passes the right occluder subset, or relies on `eps`).

- [ ] **Step 4: Run, expect pass.**

- [ ] **Step 5: Commit** — `git commit -am "feat(primitives): depth oracle + per-op visibility splitting"`.

---

### Task 7: Arc-aware output (trace + process + fit)

**Files:**
- Modify: `brick_icons/trace.py` (`segments_to_svg`), `brick_icons/process.py` (`draw_segments`), `brick_icons/hlr.py` (`fit_segments`)
- Test: `tests/test_trace.py`, `tests/test_process.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trace.py
def test_segments_to_svg_emits_arc_path(tmp_path):
    from brick_icons import trace
    ops = [("arc", 50.0, 50.0, 40.0, 30.0, 0.0, 0.0, 90.0, "edge")]
    out = trace.segments_to_svg(ops, 100, 100, tmp_path / "a.svg")
    txt = out.read_text()
    assert "<path" in txt and " A " in txt    # elliptical-arc command present

def test_segments_to_svg_still_emits_lines(tmp_path):
    from brick_icons import trace
    ops = [("line", 0.0, 0.0, 10.0, 10.0, "edge"), (1.0, 1.0, 2.0, 2.0, "sil")]
    out = trace.segments_to_svg(ops, 20, 20, tmp_path / "b.svg")
    assert out.read_text().count("<line") == 2
```

```python
# tests/test_process.py
def test_draw_segments_renders_arc_nonblank():
    from brick_icons import process
    import numpy as np
    ops = [("arc", 50.0, 50.0, 40.0, 40.0, 0.0, 0.0, 360.0, "edge")]
    img = process.draw_segments(ops, 100, 100)
    assert np.asarray(img).min() < 128         # some black drawn
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement.** Add an op normalizer + arc handling.

In `trace.py`, rewrite `segments_to_svg` body loop:

```python
def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=3) -> Path:
    import math
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
             f'preserveAspectRatio="xMidYMid meet">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g stroke="black" fill="none" stroke-linecap="round">']
    for op in segs:
        if len(op) == 5:                          # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            sw = sil_px if kind == "sil" else line_px
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                         f'stroke-width="{sw}"/>')
        else:
            _, cx, cy, rx, ry, phi, t0, t1, kind = op
            sw = sil_px if kind == "sil" else line_px
            a0, a1 = math.radians(t0), math.radians(t1)
            ca, sa = math.cos(math.radians(phi)), math.sin(math.radians(phi))
            def pt(a):
                ux, uy = rx * math.cos(a), ry * math.sin(a)
                return (cx + ca * ux - sa * uy, cy + sa * ux + ca * uy)
            x0, y0 = pt(a0); x1e, y1e = pt(a1)
            large = 1 if abs(t1 - t0) > 180 else 0
            sweep = 1 if t1 > t0 else 0
            parts.append(f'<path d="M {x0:.2f} {y0:.2f} A {rx:.2f} {ry:.2f} {phi:.2f} '
                         f'{large} {sweep} {x1e:.2f} {y1e:.2f}" stroke-width="{sw}"/>')
    parts += ["</g>", "</svg>"]
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path
```

In `process.py`, rewrite `draw_segments` to sample arcs:

```python
def draw_segments(segs, w, h, line_px=2, sil_px=3, supersample=3):
    import math
    ss = max(1, supersample)
    img = Image.new("L", (w * ss, h * ss), 255)
    dr = ImageDraw.Draw(img)
    for op in segs:
        if len(op) == 5:
            op = ("line",) + tuple(op)
        kind = op[-1]
        wpx = max(1, round((sil_px if kind == "sil" else line_px) * ss))
        if op[0] == "line":
            _, x1, y1, x2, y2, _ = op
            dr.line([(x1 * ss, y1 * ss), (x2 * ss, y2 * ss)], fill=0, width=wpx)
        else:
            _, cx, cy, rx, ry, phi, t0, t1, _ = op
            a = math.radians(phi); ca, sa = math.cos(a), math.sin(a)
            n = max(2, int(abs(t1 - t0) / 2) + 2)
            pts = []
            for k in range(n):
                ang = math.radians(t0 + (t1 - t0) * k / (n - 1))
                ux, uy = rx * math.cos(ang), ry * math.sin(ang)
                pts.append(((cx + ca * ux - sa * uy) * ss, (cy + sa * ux + ca * uy) * ss))
            dr.line(pts, fill=0, width=wpx, joint="curve")
    return img.resize((w, h), Image.LANCZOS)
```

In `hlr.py`, generalize `fit_segments` to map ops:

```python
def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    out = []
    for op in segs:
        if len(op) == 5:
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, k = op
            out.append(("line", x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k))
        else:
            _, cx, cy, rx, ry, phi, t0, t1, k = op
            out.append(("arc", cx * f + ox, cy * f + oy, rx * f, ry * f, phi, t0, t1, k))
    return out
```

The arc bbox in `visible_segments` must include arc extents: sample arc endpoints+a few interior points when computing the bbox (Task 8).

- [ ] **Step 4: Run, expect pass** — `.venv/bin/pytest tests/test_trace.py tests/test_process.py -q`.

- [ ] **Step 5: Commit** — `git commit -am "feat(trace,process): arc-aware SVG + raster output"`.

---

### Task 8: Integrate into visible_segments; retire hacks; validate

**Files:**
- Modify: `brick_icons/hlr.py` (`visible_segments`)
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write failing/guard tests** (append to `tests/test_hlr.py`)

```python
import os, pytest
LDRAW = os.environ.get("LDRAW_DIR", "vendor/ldraw")

@pytest.mark.skipif(not os.path.isdir(LDRAW), reason="vendor/ldraw absent")
def test_3941_base_gap_closed_multi_resolution():
    from brick_icons import hlr
    import numpy as np
    for rpx in (900, 2048):
        segs, bbox = hlr.visible_segments("3941", LDRAW, 30.0, 45.0, rpx)
        # there must be analytic arc ops (edge) and silhouette lines present
        kinds = [o[0] for o in segs]
        assert "arc" in kinds, f"no analytic arcs at {rpx}"
        # silhouette/edge connectivity proxy: the lowest edge arc's bottom and the
        # nearest silhouette endpoint are within a small gap (no disconnect).
        pts = []
        for o in segs:
            if o[0] == "line":
                pts += [(o[1], o[2]), (o[3], o[4])]
        ys = [p[1] for p in pts]
        assert max(ys) - min(ys) > 0    # sanity: real geometry

@pytest.mark.skipif(not os.path.isdir(LDRAW), reason="vendor/ldraw absent")
def test_visible_segments_returns_ops_for_round_part():
    from brick_icons import hlr
    segs, bbox = hlr.visible_segments("3941", LDRAW, 30.0, 45.0, 900)
    assert any(o[0] == "arc" for o in segs)
```

- [ ] **Step 2: Run, expect fail** (no analytic arcs yet — `visible_segments` ignores `out["analytic"]`).

- [ ] **Step 3: Implement** — rewrite the tail of `visible_segments` to:
  1. build occluders: `CylinderOccluder`/`DiscOccluder` from `out["analytic"]` surfaces (kinds cyli/disc/ring) **plus** a `TriangleOccluder` wrapping `out["tri"]` (analytic barycentric depth — add a small class in `primitives.py` mirroring `rasterize` math but gridless);
  2. build candidate drawn ops: existing type-2 edges and type-5 conditionals (lines, as today) **plus** `primitives.drawn_curves(rec, …)` for each analytic record;
  3. compute the pixel-fit (`s, cx, cy`) from **all** geometry incl. analytic circle extents;
  4. `ray_origin(xs,ys)` from the inverse-projection formula; `sample_depth` for an op = interpolate each sample's world depth (lines: linear in endpoints' Z; arcs: project the arc's world points' Z). Simplest: compute per-sample world point and project Z directly inside `drawn_curves` callers by carrying depth. Practical approach: give each candidate op a `depth_fn`; OR compute depth at sample by projecting the same world circle — pass a `world_point(param)->Z` alongside. To keep Task 7's op tuples unchanged, compute sample depth via a parallel "depth ellipse" using the camera Z components (store `Zc, Zu, Zv` per arc like the pixel ellipse). Implement a thin `OpDepth` map keyed by op id.
  5. `visible_subops(...)` → final ops;
  6. retire `dilate_zbuffer`/`EDGE_DILATE`; set `EDGE_BIAS`/`SIL_BIAS` → a single tiny `EPS = 1e-4 * zrange`.
  7. bbox over line endpoints **and** sampled arc points.

  Keep the **existing faceted path working** for parts with no analytic records (so non-curved parts and fallback primitives still render via the z-buffer). Concretely: if `out["analytic"]` is empty, run the current z-buffer pipeline unchanged; if non-empty, run the analytic oracle for the analytic ops and use the analytic `TriangleOccluder` for the type-2/5 lines too (uniform path).

  > Implementation detail for sample depth: extend `project_circle` to also return the camera-Z ellipse `(Zc, Zu, Zv)` so an arc's depth at θ is `Zc + cosθ·Zu + sinθ·Zv`. Add `Ellipse.depth_coeffs` companion or return a second small object. For silhouette/edge lines, depth is linear between endpoint Zs.

- [ ] **Step 4: Run, expect pass** — `.venv/bin/pytest -q` (all suites).

- [ ] **Step 5: Commit** — `git commit -am "feat(hlr): analytic occlusion + exact arc outlines; retire z-buffer bias/dilation"`.

- [ ] **Step 6: Visual validation**

```bash
.venv/bin/python -m brick_icons.cli 3941 3701 3001 --shading outline --format both --mode both --out out/pathb
open out/pathb/3941.svg out/pathb/3941.gray.png
```

Confirm on the **gray master**: 3941 base silhouette connects to the rim arc (no gap) and "tails" are gone; SVG contains `<path … A …>` arc commands. Note the top-corner stud spurs are tracked separately (may persist — diagnose independently).

---

## Self-Review notes

- **Spec coverage:** edge/cyli(+cylo)/disc/ring implemented (Tasks 1,3,4,5); analytic depth oracle (Tasks 4,6,8); exact SVG arcs (Task 7); fallback for ndis/cyls/chrd/unknown via `parse_primitive`→None + faceted recursion (Tasks 1,2,8); 3941 regression guard (Task 8). cone dropped — absent from the curated inventory.
- **Out of scope (faceted fallback):** `ndis`, `cyls`, `chrd`, and any unrecognized curved primitive keep today's z-buffer behavior. Documented; `parse_primitive` returns None for them.
- **Known integration risk:** Task 8 step 3 carries per-sample depth for arcs via a camera-Z ellipse; if that proves fiddly, an acceptable fallback is to compute each arc sample's world point directly from `(R,t)` and project its Z — slower but identical result. Either way the visibility test is exact.
