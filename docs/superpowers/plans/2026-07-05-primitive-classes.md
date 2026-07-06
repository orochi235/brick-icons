# Primitive Class Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the analytic-record dicts (`{"kind", "sector", "inner", "R", "t"}`) and their ~20 `rec["kind"]` dispatch sites with a `Primitive` class hierarchy (`Edge/Disc/Ring/Cylinder/Cone`) plus a `Projection` value object — a pure refactor with byte-identical SVG output.

**Architecture:** New classes are built alongside the existing module functions (Tasks 2–7), each ported body verbatim so numeric behavior is preserved. Task 8 flips `hlr.py`/`shade.py` to the new API, deletes the old functions, and converts every test in one commit — the only task where the two worlds must swap atomically. Task 1 snapshots specimen SVGs; Task 9 proves the output is byte-identical.

**Tech Stack:** Python 3.11+ (dataclasses with `kw_only`), numpy, pytest. Spec: `docs/superpowers/specs/2026-07-05-primitive-classes-design.md`.

**Commands:** run tests with `.venv/bin/python -m pytest -q` (or a single test with `-k`). Render specimens with `.venv/bin/brick-icons --list specimens.txt --root . --format svg --out <dir>`.

**Ground rules for the port:**
- Copy numeric expressions **verbatim** from the old bodies — same epsilons, same operation order, same `np.linspace` counts. Any change shows up as a specimen byte-diff in Task 9 and is a bug.
- Move docstrings with the code (they carry hard-won gotchas: rim suppression, ring-hole logic, interior walls, ndis-stays-faceted).
- The word "rec" is retired: new code says `prim` / `analytic` (list of primitives); the face-dict key becomes `"prim"`.

---

### Task 1: Baseline — green suite + specimen SVG snapshot

**Files:** none created in-repo (baseline goes to gitignored `debug/`).

- [ ] **Step 1: Confirm the suite is green before touching anything**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (~180). If not, STOP and report — the safety net must be intact first.

- [ ] **Step 2: Render the specimen baseline**

```bash
mkdir -p debug/prim-refactor
.venv/bin/brick-icons --list specimens.txt --root . --format svg --out debug/prim-refactor/baseline
```

Expected: one `.svg` per specimen id in `debug/prim-refactor/baseline/` (18 parts; some may emit gray+mono variants — whatever appears is the baseline).

- [ ] **Step 3: Verify the renderer is deterministic (the harness is worthless otherwise)**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg --out debug/prim-refactor/baseline2
cd debug/prim-refactor && find baseline -name '*.svg' -exec shasum -a 256 {} + | sed 's/baseline\///' | sort > baseline.sha
find baseline2 -name '*.svg' -exec shasum -a 256 {} + | sed 's/baseline2\///' | sort > baseline2.sha
diff baseline.sha baseline2.sha && echo DETERMINISTIC
cd ../..
```

Expected: `DETERMINISTIC`. If SVGs differ between identical runs, STOP and report (the byte-diff acceptance gate needs rethinking; do not proceed on a flaky baseline).

- [ ] **Step 4: No commit** (nothing in-repo changed). Keep `debug/prim-refactor/baseline.sha` for Task 9.

---

### Task 2: `Projection` value object

**Files:**
- Modify: `brick_icons/primitives.py` (add imports + class after the module docstring/imports)
- Test: `tests/test_primitives.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_primitives.py`)

```python
def test_projection_to_AB_matches_hlr_project():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, s=2.0, cx=1.0, cy=-3.0, half=100.0)
    Pw = np.array([[1.0, 2.0, 3.0], [-4.0, 0.5, 9.0]])
    a, b, z = proj.to_AB(Pw)
    ea, eb, ez = hlr.project(Pw, right, up, fwd)
    assert np.allclose(a, ea) and np.allclose(b, eb) and np.allclose(z, ez)


def test_projection_px_roundtrip_through_ray_origin():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(20.0, 60.0)
    proj = P.Projection(right, up, fwd, s=3.0, cx=0.5, cy=1.5, half=200.0)
    Pw = np.array([[10.0, -5.0, 2.0]])
    px, py, _ = proj.to_px(Pw)
    O = proj.ray_origin(px, py)
    # the ray origin projects back to the same pixel (depth-free component)
    px2, py2, _ = proj.to_px(O)
    assert np.allclose(px, px2) and np.allclose(py, py2)


def test_projection_circle_matches_project_circle():
    from brick_icons import hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, s=2.0, cx=1.0, cy=-3.0, half=100.0)

    def to_AB(Pw):
        return hlr.project(np.atleast_2d(np.asarray(Pw, float)), right, up, fwd)

    ell_old = P.project_circle(np.eye(3), np.zeros(3), 2.0, to_AB,
                               s=2.0, cx=1.0, cy=-3.0, half=100.0)
    ell_new = proj.circle(np.eye(3), np.zeros(3), 2.0)
    assert np.allclose(ell_old.center, ell_new.center)
    assert np.allclose(ell_old.u, ell_new.u) and np.allclose(ell_old.v, ell_new.v)
    assert np.allclose(ell_old.depth_coeffs, ell_new.depth_coeffs)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k projection`
Expected: FAIL — `AttributeError: ... has no attribute 'Projection'`

- [ ] **Step 3: Implement.** In `brick_icons/primitives.py`, add to the imports `from dataclasses import dataclass` and `from collections import defaultdict` (defaultdict is used in Task 7), then add after the `ALIAS_REFS` block:

```python
@dataclass(frozen=True, eq=False)
class Projection:
    """Camera + pixel-fit context for one render.

    Bundles the view basis and the pixel fit so geometry code takes one
    argument instead of seven. to_AB mirrors hlr.project (A, B image-down,
    Z = camera depth); to_px applies the pixel fit; ray_origin inverts it
    back to world ray origins for the occlusion oracle.
    """
    right: np.ndarray
    up: np.ndarray
    fwd: np.ndarray
    s: float
    cx: float
    cy: float
    half: float

    def to_AB(self, P):
        P = np.asarray(P, float)
        return P @ self.right, -(P @ self.up), P @ self.fwd

    def to_px(self, P):
        a, b, z = self.to_AB(P)
        return ((a - self.cx) * self.s + self.half,
                (b - self.cy) * self.s + self.half, z)

    def ray_origin(self, xs, ys):
        a = (np.asarray(xs, float) - self.half) / self.s + self.cx
        b = (np.asarray(ys, float) - self.half) / self.s + self.cy
        return a[:, None] * self.right - b[:, None] * self.up

    def circle(self, R, t, radius):
        """Project the world circle at (R, t, radius) into pixel space."""
        return project_circle(R, t, radius, self.to_AB,
                              self.s, self.cx, self.cy, self.half)
```

Note `to_AB` must accept both `(N,3)` and `(3,)` inputs the way the old closures did — `P @ right` handles both; do NOT add `atleast_2d` (the cone apex path indexes `[0]` on a 1-element result, and `project_circle` passes `(3,3)` stacks).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS (all, old and new)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): Projection value object for camera/pixel-fit context"
```

---

### Task 3: `Primitive` hierarchy skeleton + `from_ref` + cached `occluder()`

**Files:**
- Modify: `brick_icons/primitives.py` (add classes AFTER the occluder classes — they reference `CylinderOccluder` etc. at call time, but keeping definition order readable matters; place the hierarchy after `TriangleOccluder`)
- Test: `tests/test_primitives.py` (append)

- [ ] **Step 1: Write the failing tests**

```python
def test_from_ref_constructs_each_kind():
    R, t = np.eye(3), np.zeros(3)
    e = P.from_ref("1-4edge.dat", R, t)
    assert isinstance(e, P.Edge) and e.kind == "edge" and e.sector == 90.0
    c = P.from_ref("4-4cylo.dat", R, t)          # cylo aliases to cylinder
    assert isinstance(c, P.Cylinder) and c.kind == "cyli" and c.is_full
    d = P.from_ref("3-4disc.dat", R, t)
    assert isinstance(d, P.Disc) and d.sector == 270.0
    r = P.from_ref("4-4ring3.dat", R, t)
    assert isinstance(r, P.Ring) and r.inner == 3
    k = P.from_ref("1-16con13.dat", R, t)
    assert isinstance(k, P.Cone) and k.top == 13.0 and np.isclose(k.sector, 22.5)
    assert P.from_ref("4-4ndis.dat", R, t) is None
    assert P.from_ref("1-4cyls.dat", R, t) is None


def test_primitive_normalizes_arrays_and_is_full():
    c = P.Cylinder(R=[[1, 0, 0], [0, 1, 0], [0, 0, 1]], t=[0, 0, 0], sector=360.0)
    assert isinstance(c.R, np.ndarray) and isinstance(c.t, np.ndarray)
    assert c.is_full
    assert not P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=90.0).is_full


def test_occluder_types_and_caching():
    R, t = np.eye(3), np.zeros(3)
    assert P.Edge(R=R, t=t, sector=360.0).occluder() is None
    d = P.Disc(R=R, t=t, sector=360.0)
    assert isinstance(d.occluder(), P.DiscOccluder)
    assert np.isclose(d.occluder().inner, 0.0) and np.isclose(d.occluder().outer, 1.0)
    r = P.Ring(R=R, t=t, sector=360.0, inner=2)
    assert np.isclose(r.occluder().inner, 2.0) and np.isclose(r.occluder().outer, 3.0)
    c = P.Cylinder(R=R, t=t, sector=360.0)
    assert isinstance(c.occluder(), P.CylinderOccluder)
    k = P.Cone(R=R, t=t, sector=360.0, top=2.0)
    assert isinstance(k.occluder(), P.ConeOccluder) and k.occluder().top == 2.0
    # cached: same instance every call (hlr keys ordering maps off this)
    assert c.occluder() is c.occluder()


def test_primitive_identity_semantics():
    a = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    b = P.Cylinder(R=np.eye(3), t=np.zeros(3), sector=360.0)
    assert a != b and len({a, b}) == 2            # eq/hash by identity
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k "from_ref or occluder_types or identity or normalizes"`
Expected: FAIL — `AttributeError: module ... has no attribute 'from_ref'`

- [ ] **Step 3: Implement.** Add after `TriangleOccluder` in `brick_icons/primitives.py`:

```python
@dataclass(eq=False, kw_only=True)
class Primitive:
    """One substituted analytic primitive under world transform p -> R @ p + t.

    Identity semantics (eq=False): faces reference their source primitive and
    hlr keys ordering maps by instance, so two geometrically equal primitives
    must stay distinct. kind is the stable string used in face dicts and SVG
    op tags.
    """
    R: np.ndarray
    t: np.ndarray
    sector: float = 360.0

    kind = None          # class attribute, overridden per subclass

    def __post_init__(self):
        self.R = np.asarray(self.R, float)
        self.t = np.asarray(self.t, float)

    @property
    def is_full(self):
        return self.sector >= 360.0 - 1e-9

    def occluder(self):
        """Cached analytic occlusion surface; None for stroke-only kinds.
        Cached so every consumer (global occluder list, silhouette self-
        exclusion, witness ordering) sees the SAME instance."""
        try:
            return self._occ
        except AttributeError:
            self._occ = self._make_occluder()
            return self._occ

    def _make_occluder(self):
        return None


@dataclass(eq=False, kw_only=True)
class Edge(Primitive):
    """Drawn circle arc; no surface."""
    kind = "edge"


@dataclass(eq=False, kw_only=True)
class Disc(Primitive):
    """Filled circle in the local XZ plane."""
    kind = "disc"

    def _make_occluder(self):
        return DiscOccluder(self.R, self.t, self.sector, 0.0, 1.0)


@dataclass(eq=False, kw_only=True)
class Ring(Primitive):
    """Annulus: inner radius `inner`, outer `inner + 1`."""
    kind = "ring"
    inner: int = 1

    def _make_occluder(self):
        return DiscOccluder(self.R, self.t, self.sector,
                            self.inner, self.inner + 1)


@dataclass(eq=False, kw_only=True)
class Cylinder(Primitive):
    """Wall of a finite cylinder: radius 1, axis from t to t + A."""
    kind = "cyli"

    def _make_occluder(self):
        return CylinderOccluder(self.R, self.t, self.sector)


@dataclass(eq=False, kw_only=True)
class Cone(Primitive):
    """Truncated-cone wall: local radius top+1 at y=0 tapering to `top` at
    y=1. `top` is a float: merged smooth stacks produce non-integer values."""
    kind = "con"
    top: float = 0.0

    def _make_occluder(self):
        return ConeOccluder(self.R, self.t, self.sector, self.top)


_KIND_CLASSES = {"edge": Edge, "cyli": Cylinder, "disc": Disc}


def from_ref(name, R, t):
    """Construct the Primitive for an LDraw subfile reference, or None to
    fall back to faceted recursion (see parse_primitive for what is and is
    not substitutable, and why ndis stays faceted)."""
    spec = parse_primitive(name)
    if spec is None:
        return None
    kind, sector, inner = spec
    if kind == "ring":
        return Ring(R=R, t=t, sector=sector, inner=inner)
    if kind == "con":
        return Cone(R=R, t=t, sector=sector, top=float(inner))
    return _KIND_CLASSES[kind](R=R, t=t, sector=sector)
```

Note: `kind = None` / `kind = "edge"` are deliberately **un-annotated** class attributes so the dataclass machinery does not treat them as fields.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): Primitive dataclass hierarchy with from_ref and cached occluders"
```

---

### Task 4: geometry methods — `ring_pts`, `radius_at`, `fit_pts`, `wall_rims`

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py` (append)

The old sources being ported: `shade._radius_pts` (shade.py:18–32), `primitives.wall_rims` (primitives.py:370–405), `hlr._analytic_circle_pts` (hlr.py:298–311). Old functions stay untouched until Task 8; parity tests pin the port.

- [ ] **Step 1: Write the failing tests**

```python
def test_ring_pts_matches_shade_radius_pts():
    from brick_icons import shade
    R = np.diag([2.0, 3.0, 2.0]); t = np.array([1.0, 0.0, -1.0])
    th = np.linspace(0.0, 2 * np.pi, 17)
    cases = [
        (P.Cylinder(R=R, t=t, sector=360.0),
         {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}),
        (P.Ring(R=R, t=t, sector=360.0, inner=2),
         {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": t}),
        (P.Cone(R=R, t=t, sector=360.0, top=3.0),
         {"kind": "con", "sector": 360.0, "inner": 3, "R": R, "t": t}),
    ]
    for prim, rec in cases:
        for level in (0.0, 0.5, 1.0):
            assert np.allclose(prim.ring_pts(th, level),
                               shade._radius_pts(rec, th, level))
        assert np.allclose(prim.ring_pts(th, 0.0, radius=0.25),
                           shade._radius_pts(rec, th, 0.0, radius=0.25))


def test_wall_rims_method_matches_module_function():
    R = np.diag([20.0, -24.0, 20.0]); t = np.array([0.0, 24.0, 0.0])
    cases = [
        (P.Cylinder(R=R, t=t, sector=360.0),
         {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}),
        (P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=1.0),
         {"kind": "con", "sector": 360.0, "inner": 1, "R": np.eye(3), "t": np.zeros(3)}),
        (P.Cone(R=np.eye(3), t=np.zeros(3), sector=360.0, top=0.0),
         {"kind": "con", "sector": 360.0, "inner": 0, "R": np.eye(3), "t": np.zeros(3)}),
        (P.Ring(R=np.eye(3), t=np.zeros(3), sector=360.0, inner=2),
         {"kind": "ring", "sector": 360.0, "inner": 2, "R": np.eye(3), "t": np.zeros(3)}),
    ]
    for prim, rec in cases:
        assert prim.wall_rims() == P.wall_rims(rec)


def test_fit_pts_matches_hlr_analytic_circle_pts():
    from brick_icons import hlr
    R = np.diag([10.0, 10.0, 10.0]); t = np.zeros(3)
    cases = [
        (P.Edge(R=R, t=t, sector=90.0),
         {"kind": "edge", "sector": 90.0, "inner": 0, "R": R, "t": t}),
        (P.Cylinder(R=R, t=t, sector=360.0),
         {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}),
        (P.Cone(R=R, t=t, sector=360.0, top=2.0),
         {"kind": "con", "sector": 360.0, "inner": 2, "R": R, "t": t}),
        (P.Ring(R=R, t=t, sector=360.0, inner=3),
         {"kind": "ring", "sector": 360.0, "inner": 3, "R": R, "t": t}),
    ]
    for prim, rec in cases:
        assert np.allclose(prim.fit_pts(), hlr._analytic_circle_pts(rec))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k "ring_pts or wall_rims_method or fit_pts"`
Expected: FAIL — `AttributeError: 'Cylinder' object has no attribute 'ring_pts'`

- [ ] **Step 3: Implement.** Add to the `Primitive` base class:

```python
    def radius_at(self, level):
        """Unit-circle radius (in primitive units) at `level` along the axis."""
        return 1.0

    def ring_pts(self, thetas, level, radius=None):
        """World points on the primitive's circle at `thetas` (radians),
        `level` along the axis (0 = base ring, 1 = top ring). `radius`
        overrides the default radius_at(level)."""
        if radius is None:
            radius = self.radius_at(level)
        U, A, V = self.R[:, 0], self.R[:, 1], self.R[:, 2]
        base = self.t + level * A
        return base + radius * (np.cos(thetas)[:, None] * U
                                + np.sin(thetas)[:, None] * V)

    def fit_pts(self, n=16):
        """World sample points on the primary circle(s), for the pixel fit."""
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return self.ring_pts(ang, 0.0)

    def _rim_circles(self):
        """([(center, radius, side)], slope) for wall kinds; ([], 0.0)
        otherwise. side is +-1 along +A; slope is d(radius)/d(height)."""
        return [], 0.0

    def wall_rims(self):
        """[(key, side, slope)] for a WALL's rim circles (Cylinder/Cone).

        `side` is which side of the circle plane the wall lies on (+-1 along
        the key's canonical axis); `slope` is d(radius)/d(height) in that
        canonical direction, rounded. A rim arc is suppressed iff a FULL-
        sector wall with EQUAL slope lies on the OPPOSITE side (stacked
        cone/cylinder sections, e.g. 4589's con3-on-con4 joint) — only then
        is the whole rim a smooth joint. Same-side sharing, unequal slopes
        (creases), or partial-sector sharers (3941's base lip: 45-degree
        sectors with cutout gaps, where the body's rim stays a real edge)
        keep the arc."""
        rims, rate = self._rim_circles()
        if not rims:
            return []
        A = self.R[:, 1]
        ahat = A / (np.linalg.norm(A) or 1.0)
        out = []
        for C, radius, side in rims:
            key = rim_key(C, A, radius)
            aligned = float(np.dot(ahat, key[1])) > 0
            out.append((key,
                        side if aligned else -side,
                        round(rate if aligned else -rate, 3)))
        return out
```

Override in `Ring`:

```python
    def radius_at(self, level):
        return self.inner + 1
```

Override in `Cylinder`:

```python
    def _rim_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, ru, +1), (self.t + A, ru, -1)], 0.0

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])
```

Override in `Cone`:

```python
    def radius_at(self, level):
        return self.top + 1 - level                     # top+1 at base -> top

    def _rim_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        ah = float(np.linalg.norm(A)) or 1.0
        rate = -ru / ah                                 # radius shrinks toward +A
        rims = [(self.t, (self.top + 1) * ru, +1)]
        if self.top > 0:
            rims.append((self.t + A, self.top * ru, -1))
        return rims, rate

    def fit_pts(self, n=16):
        ang = np.linspace(0.0, math.radians(self.sector), n)
        return np.vstack([self.ring_pts(ang, 0.0),      # base + top rings
                          self.ring_pts(ang, 1.0)])
```

**Porting caution (parity trap):** old `_analytic_circle_pts` used outer radius `inner + 1` for **ring and con** at the base and `inner` for the con top ring; `radius_at` reproduces exactly that (`Ring: inner+1` level-independent; `Cone: top+1-level`). Old `wall_rims` cyli order was `[(base, +1), (top, -1)]` — preserve it; `drawn_with_depth`'s skip flags index `rims[0]`=base, `rims[1]`=top.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): ring_pts/fit_pts/wall_rims as Primitive methods"
```

---

### Task 5: `drawn_with_depth(proj, skip_rims)` methods

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py` (append)

Port of the module-level `drawn_with_depth` (primitives.py:408–486), split per kind. The module function stays until Task 8.

- [ ] **Step 1: Write the failing parity tests**

```python
def _parity_proj():
    # A=x, B=y, depth=-z  (to_AB: right=+x; B=-(P@up) => up=(0,-1,0); Z: fwd=(0,0,-1))
    return P.Projection(np.array([1.0, 0.0, 0.0]), np.array([0.0, -1.0, 0.0]),
                        np.array([0.0, 0.0, -1.0]), s=1.0, cx=0.0, cy=0.0, half=0.0)


def _op_parity(prim, rec, skip_rims=None):
    proj = _parity_proj()

    def to_AB(Pw):
        return proj.to_AB(np.atleast_2d(np.asarray(Pw, float)))

    old = P.drawn_with_depth(rec, to_AB, 1.0, 0.0, 0.0, 0.0, proj.fwd,
                             skip_rims=skip_rims)
    new = prim.drawn_with_depth(proj, skip_rims=skip_rims)
    assert len(old) == len(new)
    for (op_o, fn_o), (op_n, fn_n) in zip(old, new):
        assert op_o[0] == op_n[0] and op_o[-1] == op_n[-1]
        assert np.allclose(op_o[1:-1], op_n[1:-1])
        params = np.linspace(0.0, 1.0, 5) if op_o[0] == "line" \
            else np.linspace(op_o[7], op_o[8], 5)
        assert np.allclose(fn_o(params), fn_n(params))


def test_drawn_parity_all_kinds():
    R, t = np.eye(3), np.zeros(3)
    _op_parity(P.Edge(R=R, t=t, sector=360.0),
               {"kind": "edge", "sector": 360.0, "inner": 0, "R": R, "t": t})
    _op_parity(P.Disc(R=R, t=t, sector=270.0),
               {"kind": "disc", "sector": 270.0, "inner": 0, "R": R, "t": t})
    _op_parity(P.Ring(R=R, t=t, sector=360.0, inner=2),
               {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": t})
    _op_parity(P.Cylinder(R=R, t=t, sector=360.0),
               {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t})
    _op_parity(P.Cylinder(R=R, t=t, sector=90.0),
               {"kind": "cyli", "sector": 90.0, "inner": 0, "R": R, "t": t})
    _op_parity(P.Cone(R=R, t=t, sector=360.0, top=1.0),
               {"kind": "con", "sector": 360.0, "inner": 1, "R": R, "t": t})
    _op_parity(P.Cone(R=R, t=t, sector=360.0, top=0.0),   # apex cone
               {"kind": "con", "sector": 360.0, "inner": 0, "R": R, "t": t})


def test_drawn_parity_with_skip_rims():
    R, t = np.eye(3), np.zeros(3)
    rec = {"kind": "con", "sector": 360.0, "inner": 1, "R": R, "t": t}
    prim = P.Cone(R=R, t=t, sector=360.0, top=1.0)
    skips = {(k, s) for k, s, _ in P.wall_rims(rec)}
    _op_parity(prim, rec, skip_rims=skips)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k drawn_parity`
Expected: FAIL — `TypeError: ... drawn_with_depth() ...` / NotImplementedError (base has no method yet)

- [ ] **Step 3: Implement.** Base class gets the shared skip-flag helper and the abstract method; move the module `drawn_with_depth`'s docstring onto the base method:

```python
    def _skip_flags(self, skip_rims):
        skip_rims = skip_rims or set()
        rims = self.wall_rims() if skip_rims else []
        skip_base = bool(rims) and (rims[0][0], rims[0][1]) in skip_rims
        skip_top = len(rims) > 1 and (rims[1][0], rims[1][1]) in skip_rims
        return skip_base, skip_top

    def drawn_with_depth(self, proj, skip_rims=None):
        """Return [(op, depth_fn)] pre-occlusion drawn-op candidates.

        depth_fn maps an op's sample params to camera depth: degrees for arc
        ops, t in [0,1] for line ops. `skip_rims` is a set of (rim_key, side)
        pairs (see wall_rims) whose base/top arcs must not be emitted: rims
        where a full-sector wall continues smoothly on the other side of the
        circle plane (stacked section joints)."""
        raise NotImplementedError
```

`Edge` and `Disc` (identical bodies — two lines each, not worth a mixin):

```python
    def drawn_with_depth(self, proj, skip_rims=None):
        ell = proj.circle(self.R, self.t, 1.0)
        return [(_arc_op(ell, 0.0, self.sector, "edge"), _arc_depth_fn(ell))]
```

`Ring`:

```python
    def drawn_with_depth(self, proj, skip_rims=None):
        outer = proj.circle(self.R, self.t, self.inner + 1)
        inner = proj.circle(self.R, self.t, self.inner)
        return [(_arc_op(outer, 0.0, self.sector, "edge"), _arc_depth_fn(outer)),
                (_arc_op(inner, 0.0, self.sector, "edge"), _arc_depth_fn(inner))]
```

(The old guard `rec["inner"] > 0` is vacuous for Ring — `parse_primitive` rejects ring0 — so the inner arc is unconditional.)

`Cylinder` (port of the `kind == "cyli"` branch, comments included):

```python
    def drawn_with_depth(self, proj, skip_rims=None):
        skip_base, skip_top = self._skip_flags(skip_rims)
        U, A, V = self.R[:, 0], self.R[:, 1], self.R[:, 2]
        fwd = np.asarray(proj.fwd, float)
        # silhouette generators: radial normal perpendicular to view ->
        # cos t (U.fwd) + sin t (V.fwd) = 0  ->  t = atan2(-(U.fwd), (V.fwd)).
        uf, vf = float(U @ fwd), float(V @ fwd)
        theta = math.atan2(-uf, vf)
        base = proj.circle(self.R, self.t, 1.0)
        top = proj.circle(self.R, self.t + A, 1.0)
        pairs = []
        for th in (theta, theta + math.pi):
            deg = math.degrees(th) % 360.0
            if self.is_full or deg <= self.sector + 1e-6:
                pb, pt = base.point(th), top.point(th)
                op = ("line", float(pb[0]), float(pb[1]),
                      float(pt[0]), float(pt[1]), "sil")
                pairs.append((op, _line_depth_fn(base.depth(th), top.depth(th))))
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, self.sector, "edge"),
                          _arc_depth_fn(base)))
        if not skip_top:
            pairs.append((_arc_op(top, 0.0, self.sector, "edge"),
                          _arc_depth_fn(top)))
        return pairs
```

`Cone` (port of the `kind == "con"` branch, comments included):

```python
    def drawn_with_depth(self, proj, skip_rims=None):
        skip_base, skip_top = self._skip_flags(skip_rims)
        N = float(self.top)
        A3 = self.R[:, 1]
        fwd = np.asarray(proj.fwd, float)
        base = proj.circle(self.R, self.t, N + 1.0)
        topc = proj.circle(self.R, self.t + A3, N) if N > 0 else None
        if topc is None:                        # apex: project the point itself
            pxa, pya, zz = proj.to_px((self.t + A3)[None, :])
            apex_xy = (pxa[0], pya[0])
            apex_z = float(zz[0])
        pairs = []
        # silhouette generators: local cone normal is constant along a
        # generator, m(th) = (cos th, 1, sin th); world n.fwd = 0 reduces via
        # g = R^-1 @ fwd to g0 cos th + g2 sin th = -g1 (0, 1, or 2 solutions).
        g = np.linalg.inv(self.R) @ fwd
        A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(A_, B_)
        if hyp > 1e-12 and abs(C_) <= hyp:
            phi0 = math.atan2(B_, A_)
            dth = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            for th in (phi0 + dth, phi0 - dth):
                deg = math.degrees(th) % 360.0
                if self.is_full or deg <= self.sector + 1e-6:
                    pb = base.point(th)
                    if topc is not None:
                        pt_, zt = topc.point(th), topc.depth(th)
                    else:
                        pt_, zt = apex_xy, apex_z
                    op = ("line", float(pb[0]), float(pb[1]),
                          float(pt_[0]), float(pt_[1]), "sil")
                    pairs.append((op, _line_depth_fn(base.depth(th), zt)))
        if not skip_base:
            pairs.append((_arc_op(base, 0.0, self.sector, "edge"),
                          _arc_depth_fn(base)))
        if topc is not None and not skip_top:
            pairs.append((_arc_op(topc, 0.0, self.sector, "edge"),
                          _arc_depth_fn(topc)))
        return pairs
```

**Porting cautions:**
- The old apex projection was `(aa[0]-cx)*s+half, (bb[0]-cy)*s+half` on the raw `to_AB` result — `proj.to_px` is the identical expression; keep the `[None, :]` so a 1-row 2-D array goes in.
- `self.is_full` is exactly the old `sector >= 360.0 - 1e-9`; the `deg <= sector + 1e-6` epsilon stays.
- Old code emitted apex-cone sil line endpoints as `float(pt_[0])` where `pt_` was the `apex_xy` tuple — numerically identical here.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): drawn_with_depth as per-kind Primitive methods"
```

---

### Task 6: `faces(proj)` methods (fill geometry moves out of shade)

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py` (append)

Ports: `shade.faces_from_analytic`'s disc/ring branch (shade.py:137–163), `shade._arc_sector_spans` (173–191), `shade._cyl_wall_faces` (194–215), `shade._con_wall_faces` (218–253), `shade._wall_span_face` (256–288). Shade's copies stay until Task 8. New face dicts use key `"prim"`; parity tests compare all OTHER keys against shade's `"rec"` output.

- [ ] **Step 1: Write the failing parity tests**

```python
def _face_parity(prim, rec):
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, s=2.0, cx=0.5, cy=-0.5, half=100.0)
    old = shade.faces_from_analytic([rec], right, up, fwd,
                                    proj.s, proj.cx, proj.cy, proj.half)
    new = prim.faces(proj)
    assert len(old) == len(new)
    for fo, fn in zip(old, new):
        assert fo["kind"] == fn["kind"]
        assert fn["prim"] is prim
        assert np.allclose(fo["poly"], fn["poly"])
        assert np.allclose(fo["zs"], fn["zs"])
        assert np.isclose(fo["depth"], fn["depth"])
        for k in ("normal", "holes"):
            assert (k in fo) == (k in fn)
            if k in fo:
                assert np.allclose(np.asarray(fo[k]), np.asarray(fn[k]))
        assert fo.get("interior") == fn.get("interior")
        if "grad_axis" in fo:
            assert np.allclose(fo["grad_axis"], fn["grad_axis"])
            assert np.isclose(fo["span_deg"], fn["span_deg"])
            for (oo, ono), (no, nno) in zip(fo["grad_samples"], fn["grad_samples"]):
                assert np.isclose(oo, no) and np.allclose(ono, nno)


def test_faces_parity_all_kinds():
    R, t = np.eye(3), np.zeros(3)
    _face_parity(P.Edge(R=R, t=t, sector=360.0),
                 {"kind": "edge", "sector": 360.0, "inner": 0, "R": R, "t": t})
    _face_parity(P.Disc(R=R, t=t, sector=360.0),
                 {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t})
    _face_parity(P.Ring(R=R, t=t, sector=360.0, inner=2),     # real bore hole
                 {"kind": "ring", "sector": 360.0, "inner": 2, "R": R, "t": t})
    _face_parity(P.Ring(R=R, t=t, sector=90.0, inner=2),      # partial: concat poly
                 {"kind": "ring", "sector": 90.0, "inner": 2, "R": R, "t": t})
    _face_parity(P.Cylinder(R=R, t=t, sector=360.0),
                 {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t})
    _face_parity(P.Cylinder(R=R, t=t, sector=270.0),          # wrapped spans
                 {"kind": "cyli", "sector": 270.0, "inner": 0, "R": R, "t": t})
    _face_parity(P.Cone(R=np.diag([10.0, 10.0, 10.0]), t=t, sector=360.0, top=2.0),
                 {"kind": "con", "sector": 360.0, "inner": 2,
                  "R": np.diag([10.0, 10.0, 10.0]), "t": t})


def test_faces_axis_on_cylinder_no_wall():
    from brick_icons import hlr
    # axis pointing at the camera: U.fwd == V.fwd == 0 -> no wall face
    right, up, fwd = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    proj = P.Projection(right, up, fwd, s=1.0, cx=0.0, cy=0.0, half=0.0)
    R = np.column_stack([[1.0, 0, 0], [0, 0, 1.0], [0, 1.0, 0]])   # axis = +z
    assert P.Cylinder(R=R, t=np.zeros(3), sector=360.0).faces(proj) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k faces`
Expected: FAIL — Edge.faces missing / returns not implemented

- [ ] **Step 3: Implement.** First copy `_arc_sector_spans` from shade.py:173–191 into primitives.py **verbatim, docstring included** (module-level, above the classes). Then:

Base class:

```python
    def faces(self, proj):
        """Fill faces (dicts) for the shading pipeline; [] for stroke-only
        kinds. Face dicts carry pixel-space "poly", per-vertex "zs", mean
        "depth", the source "prim", and either a view-space "normal" (flat
        faces) or a linear-gradient spec (wall faces)."""
        return []

    def _flat_face(self, w, hole_w, proj):
        px, py, z = proj.to_px(w)
        n = self.R[:, 1]
        n = n / np.linalg.norm(n)
        nv = np.array([n @ proj.right, n @ proj.up, n @ proj.fwd])
        if nv[2] > 0:
            nv = -nv
        face = {"poly": np.stack([px, py], 1), "normal": nv,
                "depth": float(np.mean(z)), "zs": z, "kind": self.kind,
                "prim": self}
        if hole_w is not None:
            hx, hy, _ = proj.to_px(hole_w)
            face["holes"] = [np.stack([hx, hy], 1)]
        return face

    def _wall_span_face(self, lo, hi, interior, proj, normal_fn=None):
        U, V = self.R[:, 0], self.R[:, 2]
        ths = np.linspace(lo, hi, 40)
        top = self.ring_pts(ths, 1.0)
        bot = self.ring_pts(ths, 0.0)
        tpx, tpy, tz = proj.to_px(top)
        bpx, bpy, bz = proj.to_px(bot)
        poly = np.concatenate([np.stack([tpx, tpy], 1),
                               np.stack([bpx, bpy], 1)[::-1]], axis=0)
        zs = np.concatenate([tz, bz])
        # gradient axis: mid-height points at the span's end angles
        mid = self.ring_pts(np.array([lo, hi]), 0.5)
        mpx, mpy, _ = proj.to_px(mid)
        p0 = (float(mpx[0]), float(mpy[0])); p1 = (float(mpx[1]), float(mpy[1]))
        axis = np.array([p1[0] - p0[0], p1[1] - p0[1]])
        L2 = float(axis @ axis) or 1.0
        samples = []
        for th in np.linspace(lo, hi, 9):
            if normal_fn is None:
                n = math.cos(th) * U + math.sin(th) * V
            else:
                n = normal_fn(th)
            n = n / np.linalg.norm(n)
            if interior:
                n = -n                               # inward surface normal
            nv = np.array([n @ proj.right, n @ proj.up, n @ proj.fwd])
            p = self.ring_pts(np.array([th]), 0.5)
            ppx, ppy, _ = proj.to_px(p)
            off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
            samples.append((float(np.clip(off, 0.0, 1.0)), nv))
        return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)),
                "kind": self.kind, "prim": self, "interior": interior,
                "span_deg": math.degrees(hi - lo),
                "grad_axis": (p0, p1), "grad_samples": samples}
```

`Disc`:

```python
    def faces(self, proj):
        th = np.linspace(0.0, math.radians(self.sector), 64)
        return [self._flat_face(self.ring_pts(th, 0.0), None, proj)]
```

`Ring` (docstring comment from shade.py:141–143 preserved):

```python
    def faces(self, proj):
        sect = math.radians(self.sector)
        th = np.linspace(0.0, sect, 64)
        # Annulus: full sector gets a REAL hole ring (the bore); a partial
        # sector is a simple valid polygon, so keep the outer-forward /
        # inner-back concatenation there.
        outer = self.ring_pts(th, 0.0, radius=self.inner + 1)
        inner = self.ring_pts(th, 0.0, radius=self.inner)
        if sect >= 2 * math.pi - 1e-6:
            return [self._flat_face(outer, inner, proj)]
        w = np.concatenate([outer, inner[::-1]], axis=0)
        return [self._flat_face(w, None, proj)]
```

`Cylinder` (docstring from `_cyl_wall_faces` moves here):

```python
    def faces(self, proj):
        """Cylinder wall fills: the camera-facing outer half AND the far
        half's interior surface (visible when looking into an open tube —
        leaving it out produced 4019's white voids). Each visible span
        becomes one arc-region polygon with a linear-gradient spec; a partial
        sector can split a span in two where the arc wraps past 0."""
        U, V = self.R[:, 0], self.R[:, 2]
        a = float(U @ proj.fwd); b = float(V @ proj.fwd)
        if a == 0.0 and b == 0.0:
            return []                            # axis points at camera: no wall
        phi = math.atan2(b, a)
        theta_face = phi + math.pi               # most camera-facing angle
        sect = math.radians(self.sector)
        halves = [(theta_face - math.pi / 2, False),     # outer near half
                  (theta_face + math.pi / 2, True)]      # interior far half
        faces = []
        for start, interior in halves:
            for lo, hi in _arc_sector_spans(start, math.pi, sect):
                f = self._wall_span_face(lo, hi, interior, proj)
                if f is not None:
                    faces.append(f)
        return faces
```

`Cone` (docstring from `_con_wall_faces` moves here):

```python
    def faces(self, proj):
        """Cone wall fills. Unlike a cylinder, the front-facing arc is NOT a
        half: with g = R^-1 @ fwd and (A, B, C) = (g0, g2, -g1), n(theta).fwd
        = hyp*cos(theta - phi0) - C, so the outer wall is visible on
        (phi0+d, phi0+2pi-d) where d = acos(C/hyp) — the generator angles —
        and the interior far wall on the complement. Axis-on view (hyp ~ 0,
        or |C| >= hyp): every generator faces the same way, one full-circle
        span."""
        Minv = np.linalg.inv(self.R)
        g = Minv @ np.asarray(proj.fwd, float)
        A_, B_, C_ = float(g[0]), float(g[2]), float(-g[1])
        MT = Minv.T

        def normal_fn(th):
            return MT @ np.array([math.cos(th), 1.0, math.sin(th)])

        hyp = math.hypot(A_, B_)
        if hyp < 1e-12:
            spans = [(0.0, 2 * math.pi, float(g[1]) > 0)]
        elif abs(C_) >= hyp:
            spans = [(0.0, 2 * math.pi, C_ >= hyp)]
        else:
            phi0 = math.atan2(B_, A_)
            d = math.acos(max(-1.0, min(1.0, C_ / hyp)))
            spans = [(phi0 + d, phi0 + 2 * math.pi - d, False),
                     (phi0 - d, phi0 + d, True)]
        sect = math.radians(self.sector)
        faces = []
        for start, end, interior in spans:
            if end - start < 1e-6:
                continue
            for lo, hi in _arc_sector_spans(start, end - start, sect):
                f = self._wall_span_face(lo, hi, interior, proj,
                                         normal_fn=normal_fn)
                if f is not None:
                    faces.append(f)
        return faces
```

**Porting caution:** the ring full-sector test is `sect >= 2 * math.pi - 1e-6` in RADIANS — do NOT "simplify" to `self.is_full` (degrees, 1e-9): different epsilon, potential byte-diff on borderline sectors.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): faces() fill geometry as Primitive methods"
```

---

### Task 7: `merge_smooth_walls` moves to primitives

**Files:**
- Modify: `brick_icons/primitives.py`
- Test: `tests/test_primitives.py` (append)

Port of `shade.merge_smooth_wall_recs` (shade.py:79–126) + `shade._merged_wall_rec` (35–76). Shade's copies stay until Task 8.

- [ ] **Step 1: Write the failing tests** (ported from test_shade's merge tests, plus a synthetic-instance check)

```python
def _cone10(top, ty=0.0):
    return P.Cone(R=np.diag([10.0, 10.0, 10.0]),
                  t=np.array([0.0, ty, 0.0]), sector=360.0, top=float(top))


def test_merge_smooth_walls_stacked_cones_one_prim():
    out = P.merge_smooth_walls([_cone10(2), _cone10(1, ty=10.0)])
    assert len(out) == 1
    merged = out[0]
    assert isinstance(merged, P.Cone) and merged.is_full
    # merged frustum: base radius 30 at y=0 -> radius 10 at y=20;
    # R scale = dr = 20, top = r1/dr = 0.5
    assert np.isclose(np.linalg.norm(merged.R[:, 0]), 20.0)
    assert np.isclose(merged.top, 0.5)
    assert np.allclose(merged.t, [0.0, 0.0, 0.0])


def test_merge_smooth_walls_stacked_cylinders():
    a = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]), t=np.zeros(3), sector=360.0)
    b = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]),
                   t=np.array([0.0, 10.0, 0.0]), sector=360.0)
    out = P.merge_smooth_walls([a, b])
    assert len(out) == 1 and isinstance(out[0], P.Cylinder)
    assert np.isclose(np.linalg.norm(out[0].R[:, 1]), 20.0)   # merged height


def test_merge_smooth_walls_keeps_creases_and_partial_sectors():
    lo = _cone10(2)
    crease = P.Cylinder(R=np.diag([10.0, 10.0, 10.0]),
                        t=np.array([0.0, 10.0, 0.0]), sector=360.0)
    assert len(P.merge_smooth_walls([lo, crease])) == 2       # slope mismatch
    part = P.Cone(R=np.diag([10.0, 10.0, 10.0]),
                  t=np.array([0.0, 10.0, 0.0]), sector=90.0, top=1.0)
    assert len(P.merge_smooth_walls([lo, part])) == 2         # partial sector


def test_merge_smooth_walls_passthrough_non_walls():
    ring = P.Ring(R=np.eye(3), t=np.zeros(3), sector=360.0, inner=2)
    out = P.merge_smooth_walls([ring])
    assert out == [ring]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q -k merge_smooth_walls`
Expected: FAIL — no attribute `merge_smooth_walls`

- [ ] **Step 3: Implement.** The merge's chain-end bookkeeping needs BOTH end circles of each wall **including a radius-0 apex** (an apex is a chain end even though it has no rim arc) — that is `_end_circles`, deliberately distinct from `_rim_circles` (which omits the apex; suppression keys never form there):

`Cylinder`:

```python
    def _end_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, ru), (self.t + A, ru)]
```

`Cone`:

```python
    def _end_circles(self):
        A = self.R[:, 1]
        ru = float(np.linalg.norm(self.R[:, 0]))
        return [(self.t, (self.top + 1) * ru), (self.t + A, self.top * ru)]
```

Module level (docstrings carried over from shade with dict wording updated):

```python
def _merged_wall(members):
    """One synthetic Cylinder/Cone covering a smooth chain of wall
    primitives (sections of the same infinite cylinder/cone). Returns None
    if the chain has no clean two free rims (degenerate or looped
    sharing)."""
    ends = {}
    for p in members:
        A = p.R[:, 1]
        for C, r in p._end_circles():
            key = rim_key(C, A, r)
            if key in ends:
                del ends[key]                    # interior joint
            else:
                ends[key] = (np.asarray(C, float), float(r))
    if len(ends) != 2:
        return None
    (C0, r0), (C1, r1) = ends.values()
    if r0 < r1:
        (C0, r0), (C1, r1) = (C1, r1), (C0, r0)  # base = wide end
    A = C1 - C0
    ah = float(np.linalg.norm(A))
    if ah < 1e-9:
        return None
    ahat = A / ah
    U0 = members[0].R[:, 0]
    u = U0 - float(U0 @ ahat) * ahat
    un = float(np.linalg.norm(u))
    if un < 1e-9:
        return None
    u = u / un
    v = np.cross(u, ahat)
    dr = r0 - r1
    if dr < 1e-9:
        return Cylinder(R=np.column_stack([r0 * u, A, r0 * v]), t=C0,
                        sector=360.0)
    return Cone(R=np.column_stack([dr * u, A, dr * v]), t=C0,
                sector=360.0, top=r1 / dr)


def merge_smooth_walls(analytic):
    """Collapse chains of full-sector Cylinder/Cone primitives that continue
    each other smoothly through a shared rim — equal slope on opposite sides
    of the rim plane, the same predicate that suppresses the rim's STROKE in
    hlr — into one synthetic primitive per chain, so the wall shades as ONE
    face with ONE gradient. Left separate, each section fits its own
    gradient axis and the shared rim shows a tone step (4589's con3-on-con4
    body: identical stops over different axis extents). Non-wall primitives,
    partial sectors, creases, and ambiguously shared rims pass through
    unchanged. The synthetic Cone's `top` may be non-integer."""
    walls = [i for i, p in enumerate(analytic)
             if isinstance(p, (Cylinder, Cone)) and p.is_full]
    by_key = defaultdict(list)
    for i in walls:
        for key, side, slope in analytic[i].wall_rims():
            by_key[key].append((i, side, slope))
    parent = {i: i for i in walls}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for ent in by_key.values():
        if len(ent) != 2:
            continue                             # free rim or 3-way sharing
        (i, si, mi), (j, sj, mj) = ent
        if i == j or si != -sj or mi != mj:
            continue                             # same side, or a crease
        if type(analytic[i]) is not type(analytic[j]):
            continue
        parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in walls:
        groups[find(i)].append(i)
    synth_at, drop = {}, set()
    for members in groups.values():
        if len(members) < 2:
            continue
        prim = _merged_wall([analytic[i] for i in members])
        if prim is not None:
            synth_at[min(members)] = prim
            drop.update(members)
    if not synth_at:
        return list(analytic)
    return [synth_at.get(i, p) for i, p in enumerate(analytic)
            if i in synth_at or i not in drop]
```

**Porting caution:** the kind-equality guard becomes `type(a) is not type(b)` — exact type, not isinstance (encodes "cyli can't merge with con" without string compares).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_primitives.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "feat(primitives): merge_smooth_walls over Primitive instances"
```

---

### Task 8: THE FLIP — hlr + shade consume Primitives; old API deleted; tests converted

This is the one atomic task: producers and consumers of the rec dicts swap together. Everything here is one commit. Work through the files in order; nothing runs green until the end of the task.

**Files:**
- Modify: `brick_icons/hlr.py`
- Modify: `brick_icons/shade.py`
- Modify: `brick_icons/primitives.py` (deletions)
- Modify: `tests/test_primitives.py`, `tests/test_shade.py`, `tests/test_hlr.py`

- [ ] **Step 1: hlr.flatten constructs Primitives** (hlr.py:94–99). Replace:

```python
                spec = primitives.parse_primitive(ref)
                if spec is not None and "analytic" in out:
                    kind, sector, inner = spec
                    out["analytic"].append(
                        {"kind": kind, "sector": sector, "inner": inner,
                         "R": Rsub, "t": tsub})
```

with:

```python
                prim = primitives.from_ref(ref, Rsub, tsub)
                if prim is not None and "analytic" in out:
                    out["analytic"].append(prim)
```

- [ ] **Step 2: hlr analytic pipeline.** Delete `_analytic_circle_pts` (hlr.py:298–311) entirely. Replace the body of `_visible_segments_analytic` (hlr.py:314–422) with:

```python
def _visible_segments_analytic(out, right, up, fwd, render_px):
    """Exact pipeline: analytic occlusion oracle + true arc/line drawn ops."""
    analytic = out["analytic"]
    half = render_px / 2.0

    cloud = []
    if out["tri"]:
        cloud.append(np.array(out["tri"]).reshape(-1, 3))
    if out["2"]:
        cloud.append(np.array(out["2"]).reshape(-1, 3))
    for prim in analytic:
        cloud.append(prim.fit_pts())
    allpts = np.vstack(cloud)
    s, cx, cy, zrange = _fit_params(allpts, right, up, fwd, render_px)
    eps = 1e-3 * zrange
    proj = primitives.Projection(right, up, fwd, s, cx, cy, half)

    # occluders: analytic surfaces + flat triangles. Only ORIGINAL primitives
    # join the stroke-visibility list; walls merged later inside
    # faces_from_analytic build their own (cached) occluder lazily for
    # witness ordering, and must NOT be added here — their member surfaces
    # already cover the same geometry.
    occluders = [p.occluder() for p in analytic if p.occluder() is not None]
    if out["tri"]:
        occluders.append(primitives.TriangleOccluder(np.array(out["tri"])))

    # drawn ops: analytic curves (+ a cylinder excludes itself from its
    # silhouette). A wall's rim arc is suppressed when a FULL-sector wall of
    # equal slope continues on the other side of the circle plane (stacked
    # cone/cylinder sections): that whole rim is a smooth joint, not an edge.
    full_smooth = defaultdict(set)
    for prim in analytic:
        if prim.is_full:
            for key, side, slope in prim.wall_rims():
                full_smooth[key].add((side, slope))
    shared_rims = set()
    for prim in analytic:
        for key, side, slope in prim.wall_rims():
            if (-side, slope) in full_smooth[key]:
                shared_rims.add((key, side))
    specs = []
    for prim in analytic:
        own = prim.occluder()
        for op, dfn in prim.drawn_with_depth(proj, skip_rims=shared_rims):
            specs.append((op, dfn, own if op[-1] == "sil" else None))
    # non-substituted straight edges (box edges, chords) and conditionals
    for e in out["2"]:
        px, py, z = proj.to_px(e)
        specs.append((("line", float(px[0]), float(py[0]),
                       float(px[1]), float(py[1]), "edge"),
                      primitives._line_depth_fn(float(z[0]), float(z[1]))))
    for q in out["5"]:
        px, py, z = proj.to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            specs.append((("line", float(px[0]), float(py[0]),
                           float(px[1]), float(py[1]), "sil"),
                          primitives._line_depth_fn(float(z[0]), float(z[1]))))

    segs = primitives.visible_subops(specs, occluders, proj.ray_origin, fwd,
                                     eps, n=64)
    from . import shade
    tri_faces = shade.faces_from_tris(np.array(out["tri"]), proj,
                                      cond_edges=out["5"]) if out["tri"] else []
    an_faces = shade.faces_from_analytic(analytic, proj)
    own_occ = {id(f): f["prim"].occluder() for f in an_faces
               if f["prim"].occluder() is not None}
    # Witness-depth ordering replaces both the mean-depth painter sort and the
    # occlusion cull: hidden faces paint first and get covered.
    faces = shade.order_faces(tri_faces + an_faces, proj, eps, own_occ=own_occ)
    return VisResult(segs, _ops_bbox(segs), s, faces, analytic)
```

- [ ] **Step 3: hlr faceted pipeline** (`_visible_segments_faceted`, hlr.py:249–295). After `s, cx, cy` are computed (line ~259), build `proj = primitives.Projection(right, up, fwd, s, cx, cy, render_px / 2)`. Keep the local `to_px` closure for the tri/edge/type-5 pixel math (it is used with unpacked component indexing) OR replace its uses with `proj.to_px` — same formula; replacing is cleaner. Change the faces call (line 292):

```python
    faces = shade.faces_from_tris(tri, proj, cond_edges=out["5"]) if len(tri) else []
```

(`order_faces(faces, eps=EDGE_BIAS * zrange)` on line 294 is already compatible with the new signature below.)

- [ ] **Step 4: shade.py.** Delete: `_project_px`, `_radius_pts`, `_merged_wall_rec`, `merge_smooth_wall_recs`, `_arc_sector_spans`, `_cyl_wall_faces`, `_con_wall_faces`, `_wall_span_face`. Replace `faces_from_analytic` with:

```python
def faces_from_analytic(analytic, proj):
    """Fill faces for analytic primitives, with smooth wall chains merged to
    single faces (see primitives.merge_smooth_walls)."""
    return [f for prim in primitives.merge_smooth_walls(analytic)
            for f in prim.faces(proj)]
```

Change `faces_from_tris(tri, right, up, fwd, s, cx, cy, half, cond_edges=None)` to `faces_from_tris(tri, proj, cond_edges=None)`: inside, replace `_project_px(v, right, up, fwd, s, cx, cy, half)` with `proj.to_px(v)` and every bare `right`/`up`/`fwd` (normal-to-view-space math) with `proj.right`/`proj.up`/`proj.fwd`.

Change `order_faces(faces, ray_origin=None, fwd=None, eps=1e-6, own_occ=None)` to `order_faces(faces, proj=None, eps=1e-6, own_occ=None)`: inside, `ray_origin(...)` becomes `proj.ray_origin(...)`, `fwd` becomes `proj.fwd`, and the `ray_origin is not None` guard becomes `proj is not None`.

Change `cull_occluded_faces(faces, occluders, ray_origin, fwd, eps, kinds=("tri",), own_occ=None)` to `cull_occluded_faces(faces, occluders, proj, eps, kinds=("tri",), own_occ=None)`: same substitutions.

- [ ] **Step 5: primitives.py deletions.** Delete the module-level functions `wall_rims` (370–405), `drawn_with_depth` (408–486), and `drawn_curves` (489–491) — their logic now lives on the classes. Keep `rim_key`, `_arc_op`, `arc_ellipse`, `_arc_depth_fn`, `_line_depth_fn`, `project_circle`, `_samples_for`, `_runs`, `visible_subops`, all occluder classes, `parse_primitive`, `ALIAS_REFS`. Update the module docstring's conventions note if it references record dicts.

- [ ] **Step 6: convert the tests.** Mechanical rules, applied across all three files:

| Old | New |
|---|---|
| `{"kind": "cyli", "sector": S, "inner": 0, "R": R, "t": t}` | `P.Cylinder(R=R, t=t, sector=S)` |
| `{"kind": "con", ..., "inner": N, ...}` | `P.Cone(R=R, t=t, sector=S, top=float(N))` |
| `{"kind": "ring", ..., "inner": N, ...}` | `P.Ring(R=R, t=t, sector=S, inner=N)` |
| `{"kind": "edge"/"disc", ...}` | `P.Edge(...)` / `P.Disc(...)` |
| `rec["kind"] == "con"` / `r["kind"] for r in ...` | `isinstance(p, P.Cone)` / `p.kind for p in ...` |
| `rec["R"]`, `rec["t"]`, `rec["sector"]` | `prim.R`, `prim.t`, `prim.sector` |
| `P.wall_rims(rec)` | `prim.wall_rims()` |
| `P.drawn_with_depth(rec, to_AB, s, cx, cy, half, fwd, ...)` | `prim.drawn_with_depth(proj, ...)` |
| `P.drawn_curves(rec, to_AB, s, cx, cy, half, fwd)` | `[op for op, *_ in prim.drawn_with_depth(proj)]` |
| `shade.faces_from_analytic(recs, right, up, fwd, s, cx, cy, half)` | `shade.faces_from_analytic(prims, P.Projection(right, up, fwd, s, cx, cy, half))` |
| `shade.faces_from_tris(tri, right, up, fwd, s=…, cx=…, cy=…, half=…, ...)` | `shade.faces_from_tris(tri, P.Projection(right, up, fwd, s, cx, cy, half), ...)` |
| `shade.merge_smooth_wall_recs(recs)` | `P.merge_smooth_walls(prims)` |
| `shade.cull_occluded_faces(faces, occluders, ray_origin, fwd, eps, ...)` | `shade.cull_occluded_faces(faces, occluders, proj, eps, ...)` |
| face `f["rec"]` | `f["prim"]` |

Stub-projector conversions (tests that hand-rolled `to_AB` closures become `Projection` instances; `B = -(P @ up)` fixes the `up` sign):

| Old stub | Equivalent Projection (`s=1, cx=0, cy=0, half=0`) |
|---|---|
| `A=x, B=z, Z=y` (`_proj_xz`) | `P.Projection(np.array([1.,0,0]), np.array([0,0,-1.]), np.array([0,1.,0]), 1.0, 0.0, 0.0, 0.0)` |
| `A=x, B=y, Z=z` (`proj_z`) | `P.Projection(np.array([1.,0,0]), np.array([0,-1.,0]), np.array([0,0,1.]), 1.0, 0.0, 0.0, 0.0)` |
| `A=x, B=y, Z=-z` (`_stub_proj`) | `P.Projection(np.array([1.,0,0]), np.array([0,-1.,0]), np.array([0,0,-1.]), 1.0, 0.0, 0.0, 0.0)` |
| `A=x, B=z, Z=-y` (test_cone_axis_on_view) | `P.Projection(np.array([1.,0,0]), np.array([0,0,-1.]), np.array([0,-1.,0]), 1.0, 0.0, 0.0, 0.0)` |
| `ray_origin = stack([xs, ys, 0])`, `fwd=(0,0,1)` (cull/order tests) | `P.Projection(np.array([1.,0,0]), np.array([0,-1.,0]), np.array([0,0,1.]), 1.0, 0.0, 0.0, 0.0)` — its `ray_origin` is exactly `(xs, ys, 0)` |

File-by-file worklist:

- `tests/test_primitives.py`: convert `_proj_xz`/`_stub_proj`/`proj_z` and every dict-rec test (lines 108–344: drawn ops, rim suppression suite, `_smooth_shared_rims` helper — its body becomes `p.is_full` / `p.wall_rims()`). **Delete** the Task 4/5 parity tests (`test_ring_pts_matches_shade_radius_pts`, `test_wall_rims_method_matches_module_function`, `test_fit_pts_matches_hlr_analytic_circle_pts`, `_op_parity`, `test_drawn_parity_all_kinds`, `test_drawn_parity_with_skip_rims`, `_face_parity`, `test_faces_parity_all_kinds`) — their reference implementations are gone; the CONVERTED original tests (e.g. `test_drawn_edge_is_full_arc`, `test_cone_drawn_ops_full_sector`, the rim-suppression suite) carry the coverage forward. Keep `test_faces_axis_on_cylinder_no_wall` (self-contained).
- `tests/test_shade.py`: convert constructions + `faces_from_analytic`/`faces_from_tris`/`cull_occluded_faces` call sites per the tables. The merge tests (`test_merge_smooth_wall_recs_*`, lines 169–215) were re-homed in Task 7 — delete the shade versions (coverage lives in `test_primitives.py`; keep `test_smooth_stack_shades_as_single_wall_face` (line ~217) converted, since it exercises the merge THROUGH `faces_from_analytic`). Fake-occluder cull tests keep their `FakeOcc` classes; only the `ray_origin`/`fwd` args collapse into the identity Projection from the table.
- `tests/test_hlr.py`: lines 232–234 (`isinstance(prim, primitives.Edge)`, `prim.sector`, `prim.R`, `prim.t`), 254 (`p.kind`), 278/293–297 (dict recs → `primitives.Cone(...)`), 327/337 (`p.kind` / `isinstance`). The `spy` wrapper at 303 needs no change (it passes `*a`/`**kw` through).

- [ ] **Step 7: Run the full suite; fix fallout**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, same test count as Task 1 baseline minus deleted parity/duplicate-merge tests plus the tests added in Tasks 2–7. Typical fallout to check if red: a missed dict-construction in a test, a missed `f["rec"]`, a stub Projection with the wrong `up` sign (symptom: mirrored B/y coordinates).

- [ ] **Step 8: Commit**

```bash
git add brick_icons/ tests/
git commit -m "refactor: primitives as class hierarchy; hlr/shade consume Primitive/Projection

Replaces analytic-record dicts and rec['kind'] dispatch with the
Edge/Disc/Ring/Cylinder/Cone hierarchy from the 2026-07-05 spec. Face dicts
now carry 'prim' (the source Primitive) instead of 'rec'. Byte-identical
SVG output (verified against the specimen baseline)."
```

---

### Task 9: Specimen byte-diff + closeout

- [ ] **Step 1: Render specimens post-refactor and diff against the Task 1 baseline**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg --out debug/prim-refactor/after
cd debug/prim-refactor && find after -name '*.svg' -exec shasum -a 256 {} + | sed 's/after\///' | sort > after.sha
diff baseline.sha after.sha && echo BYTE-IDENTICAL
cd ../..
```

Expected: `BYTE-IDENTICAL`. **Any diff is a refactor bug.** To localize one: `diff` the two SVG files to find the drifted element, identify which primitive kind draws it, and re-check that kind's ported method against the pre-refactor body (`git show <task1-era-commit>:brick_icons/primitives.py`) for a changed epsilon, operation order, or dropped guard. Do not rationalize a diff as "visually identical"; fix the port.

- [ ] **Step 2: Full suite one more time**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 3: Mark the spec implemented.** In `docs/superpowers/specs/2026-07-05-primitive-classes-design.md`, change `**Status:** approved for planning` to `**Status:** implemented (2026-07-05)` — adjust the date to the actual completion date.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-05-primitive-classes-design.md
git commit -m "docs: mark primitive-classes spec implemented"
```

---

## Self-review notes (already applied)

- **Spec coverage:** hierarchy + named fields (T3/T4), cached occluder collapsing rec_occ/own_occ (T3, T8 step 2), Projection incl. shade adoption (T2, T8 steps 3–4), merge move (T7), from_ref (T3), rec→prim rename (T6 face dicts, T8 step 6), deletions/clean break (T8 step 5), test conversion (T8 step 6), acceptance = suite + byte-diff (T1, T9). Risks from the spec all have a home: occluder caching test (T3), `type is` merge guard (T7), loud failure on missed dict probes (T8 step 7).
- **`_end_circles` vs `_rim_circles`:** deliberately two methods — the merge counts a radius-0 apex as a chain end; rim suppression must not (old `_merged_wall_rec` vs `wall_rims` disagreed on exactly this; collapsing them breaks apex-terminated chains like con2+con1+con0 stacks).
- **Type consistency check:** `from_ref` (T3) is what flatten calls (T8 step 1); `faces()` emits `"prim"` (T6) and hlr reads `f["prim"]` (T8 step 2); `order_faces(faces, proj, eps, own_occ=…)` call in T8 step 2 matches the T8 step 4 signature `order_faces(faces, proj=None, eps=1e-6, own_occ=None)` positionally.
