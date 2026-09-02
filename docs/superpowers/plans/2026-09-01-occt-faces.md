# OCCT faces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `occt.visible_segments` returns fill faces, so `--engine occt --shade-style flat3` fills instead of silently degrading to strokes.

**Architecture:** Faces come from the faces of `build_shape(out)` — the same sewn shape HLR draws edges from. Flat faces project their wires directly; cylinder and cone faces are cut at their limb generators and each span becomes its own face. Depth ordering hands `shade.order_faces` a `primitives.Projection` in op space plus an occluder per curved face, which is what the naive engine already does for its analytic faces.

**Tech Stack:** Python, OCP (OpenCASCADE bindings), numpy, shapely (already behind `fill_ops`), pytest.

Design: `docs/superpowers/specs/2026-09-01-occt-faces-design.md`.

---

## File Structure

- `brick_icons/occt.py` — everything here. The module docstring's claim that it is the only module importing OCP is a documented invariant in `OCCT-MIGRATION.md` and `HANDOFF.md`; a second OCP-importing module would falsify it. Grows by roughly 300 lines to ~1250, between `hlr.py` (1199) and `primitives.py` (1309).
- `brick_icons/hlr.py:1013` — pass `fwd` to `occt.visible_segments`.
- `tests/test_occt.py` — all new tests.
- `scripts/compare-engines.py` — gains `--combo` so parity can be measured on the combo where fills exist.

Nothing in the naive path is touched, so `tests/goldens/hashes.txt` must not move.

---

### Task 1: The op-space camera

`occt` writes ops in projected LDU with Y negated. `order_faces` needs a `Projection` that maps world into **that** space, or `ray_origin` inverts into the wrong place.

**Files:**
- Modify: `brick_icons/occt.py` (imports, new `op_projection`)
- Modify: `brick_icons/hlr.py:1011-1013`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def test_op_projection_matches_the_space_the_ops_are_written_in():
    """apply_affine_faces applies the canvas fit later, so the projection
    handed to order_faces carries the identity pixel fit."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    ax, ay = occt._screen_axes(right, up)
    P = np.array([[1.0, 2.0, 3.0], [-4.0, 5.0, 6.0], [0.0, 0.0, 0.0]])
    raw = occt._proj2(P, ax, ay)
    raw[:, 1] *= -1.0                      # _negate_y, applied to points
    proj = occt.op_projection(right, up, fwd)
    x, y, _ = proj.to_px(P)
    assert np.allclose(np.stack([x, y], 1), raw)


def test_op_projection_ray_origin_inverts_it():
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    P = np.array([[7.0, -2.0, 4.0]])
    x, y, _ = proj.to_px(P)
    O = proj.ray_origin(x, y)
    # the ray origin differs from P only along the view direction
    assert np.allclose(np.cross(P[0] - O[0], fwd), 0.0, atol=1e-9)


def test_forward_is_the_negated_projector_axis():
    """occt takes fwd from the caller. Anyone recomputing it locally has to
    get this sign, or every depth comparison runs backwards."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    z, _ = occt.projector_axes(right, up)
    assert np.allclose(-z / np.linalg.norm(z), fwd)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k op_projection -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute 'op_projection'`

- [x] **Step 3: Write the implementation**

In `brick_icons/occt.py`, extend the local import:

```python
from . import hlr, primitives
```

and add, next to `_screen_axes`:

```python
def op_projection(right, up, fwd):
    """The render camera in OP space -- the (A, -B) coordinates every op and
    face polygon of this engine is written in.

    The identity pixel fit is not a placeholder: cli.apply_affine_faces maps
    op space to the canvas afterwards, exactly as it does for the ops.
    """
    return primitives.Projection(np.asarray(right, float),
                                 np.asarray(up, float),
                                 np.asarray(fwd, float),
                                 s=1.0, cx=0.0, cy=0.0, half=0.0)
```

In `brick_icons/hlr.py`, change line 1013 to pass the basis through:

```python
    if engine == "occt":
        from . import occt
        return occt.visible_segments(out, right, up, render_px, cull=cull,
                                     fwd=fwd)
```

and change the signature in `occt.py`:

```python
def visible_segments(out, right, up, render_px, cull=True, fwd=None):
```

with, as its first body line:

```python
    if fwd is None:
        z, _ = projector_axes(right, up)
        fwd = -z / np.linalg.norm(z)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k "op_projection or forward_is_the_negated" -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add brick_icons/occt.py brick_icons/hlr.py tests/test_occt.py
git commit -m "give the occt engine a camera in its own op space"
```

---

### Task 2: World points along a wire

Face boundaries are sampled ON their own curves. `_edge_ops` cannot be reused: it reads HLR's already-projected output, where `Value(t).X()` is a screen coordinate. These are the shape's own 3D edges.

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def test_wire_points_of_a_circle_lie_on_that_circle():
    o = np.array([0.0, 0.0, 0.0])
    face = occt.annulus_face(o, np.array([0.0, 1.0, 0.0]),
                             np.array([1.0, 0.0, 0.0]), 0.0, 6.0,
                             2 * math.pi)
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(face))
    r = np.linalg.norm(pts - o, axis=1)
    assert np.allclose(r, 6.0, atol=1e-9)
    assert len(pts) >= 40           # 9-degree step over a full turn


def test_wire_points_of_a_polygon_are_its_corners():
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 4.0]])
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(occt.tri_face(p)))
    assert len(pts) == 3
    for corner in p:
        assert np.min(np.linalg.norm(pts - corner, axis=1)) < 1e-9


def test_wire_points_do_not_repeat_the_shared_vertex():
    """Consecutive edges share an endpoint; emitting it twice puts a
    zero-length segment in the polygon, which shapely reads as invalid."""
    p = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 4.0]])
    pts = occt._wire_points(occt.BRepTools.OuterWire_s(occt.tri_face(p)))
    d = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    assert d.min() > 1e-6
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k wire_points -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute '_wire_points'`

- [x] **Step 3: Write the implementation**

Add to the imports in `brick_icons/occt.py`:

```python
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.TopAbs import TopAbs_Orientation
```

and add, after `_edge_ops`:

```python
BOUNDARY_STEP_DEG = 9.0    # naive samples a wall span at 40 points; matched


def _edge_points(edge, step_deg=BOUNDARY_STEP_DEG):
    """World points along one edge, ON its own curve.

    A line contributes its endpoints. A circle or ellipse is sampled, because
    fill_ops takes a polygon -- but every sample sits exactly on the conic, so
    geom2d.arc_candidates reads the run back as the arc it came from.
    """
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    if c.GetType() == GeomAbs_CurveType.GeomAbs_Line:
        ts = [t0, t1]
    else:
        span = abs(math.degrees(t1 - t0))
        ts = np.linspace(t0, t1, max(2, int(math.ceil(span / step_deg)) + 1))
    P = np.array([[p.X(), p.Y(), p.Z()]
                  for p in (c.Value(float(t)) for t in ts)], float)
    if edge.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        P = P[::-1]
    return P


def _wire_points(wire, step_deg=BOUNDARY_STEP_DEG):
    """A wire as one closed loop of world points, in wire order."""
    loop = []
    ex = BRepTools_WireExplorer(wire)
    while ex.More():
        P = _edge_points(ex.Current(), step_deg)
        ex.Next()
        if loop and np.linalg.norm(P[0] - loop[-1]) < TOL:
            P = P[1:]
        loop.extend(P)
    if len(loop) > 1 and np.linalg.norm(loop[0] - loop[-1]) < TOL:
        loop = loop[:-1]
    return np.array(loop, float)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k wire_points -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "sample a face wire on its own curve"
```

---

### Task 3: Flat faces

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def _plane_faces_of(part, ldraw_dir, lat=30.0, long=45.0):
    out = occt.flatten_part(part, ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(lat, long)
    proj = occt.op_projection(right, up, fwd)
    return occt.plane_faces(shape, proj), proj


def test_a_ring_face_carries_its_bore_as_a_hole():
    o = np.zeros(3)
    face = occt.annulus_face(o, np.array([0.0, 1.0, 0.0]),
                             np.array([1.0, 0.0, 0.0]), 2.0, 6.0,
                             2 * math.pi)
    right, up, fwd = hlr.view_basis(90.0, 0.0)     # straight down the axis
    f = occt._plane_face(face, occt.op_projection(right, up, fwd))
    assert len(f["holes"]) == 1
    outer = np.linalg.norm(f["poly"] - f["poly"].mean(0), axis=1)
    inner = np.linalg.norm(f["holes"][0] - f["poly"].mean(0), axis=1)
    assert inner.max() < outer.min()


def test_a_flat_face_carries_the_fields_fill_ops_reads(ldraw_dir):
    faces, _ = _plane_faces_of("32062", ldraw_dir)
    assert faces
    for f in faces:
        assert set(f) >= {"poly", "normal", "depth", "zs", "plane", "color"}
        assert f["poly"].shape[1] == 2
        assert len(f["zs"]) == len(f["poly"])
        assert f["color"] == 16


def test_32062_is_all_flat_faces(ldraw_dir):
    """178 planes and no curved surface at all -- the part that proves the
    flat path without any limb solving."""
    out = occt.flatten_part("32062", ldraw_dir)
    kinds = _surface_types(occt.build_shape(out))
    assert set(kinds) == {"Plane"}


def test_back_faces_are_culled_without_losing_visible_area(ldraw_dir):
    """The cull is naive's rule (faces_from_tris) and exists for the witness
    sort's O(n^2): 3649 sews 846 faces. It must remove nothing that shows."""
    from shapely.ops import unary_union
    from brick_icons import geom2d
    out = occt.flatten_part("3005", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    kept = occt.plane_faces(shape, proj)
    every = occt.plane_faces(shape, proj, cull_back=False)
    assert len(kept) < len(every)
    a = unary_union([geom2d.to_geom(f["poly"], f.get("holes") or []) for f in kept])
    b = unary_union([geom2d.to_geom(f["poly"], f.get("holes") or []) for f in every])
    assert b.difference(a).area <= 0.01 * b.area
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k "flat_face or ring_face_carries or 32062_is_all or back_faces_are_culled" -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute 'plane_faces'`

- [x] **Step 3: Write the implementation**

```python
def _plane_face(face, proj, step_deg=BOUNDARY_STEP_DEG):
    """One planar face as a fill_ops face dict."""
    pl = BRepAdaptor_Surface(face).Plane()
    d = pl.Axis().Direction()
    n = np.array([d.X(), d.Y(), d.Z()], float)
    if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        n = -n
    outer = BRepTools.OuterWire_s(face)
    W = _wire_points(outer, step_deg)
    px, py, z = proj.to_px(W)
    holes = []
    ex = TopExp_Explorer(face, TopAbs_ShapeEnum.TopAbs_WIRE)
    while ex.More():
        w = TopoDS.Wire_s(ex.Current())
        ex.Next()
        if w.IsSame(outer):
            continue
        hx, hy, _ = proj.to_px(_wire_points(w, step_deg))
        holes.append(np.stack([hx, hy], 1))
    f = {"poly": np.stack([px, py], 1),
         "normal": np.array([n @ proj.right, n @ proj.up, n @ proj.fwd]),
         "depth": float(np.mean(z)), "zs": z, "kind": "occt-plane",
         # carrier plane key: fill_ops unions same-plane fragments that abut
         # without a shared edge, which is what UnifySameDomain declined to do
         "plane": (round(float(n[0]), 4), round(float(n[1]), 4),
                   round(float(n[2]), 4), round(float(n @ W[0]), 2)),
         "color": 16}
    if holes:
        f["holes"] = holes
    return f


def plane_faces(shape, proj, cull_back=True):
    """Every planar face of `shape`, camera-facing ones only by default.

    Culling matches faces_from_tris: winding is trusted (repair.repaired_tris
    fixed it upstream) and a face pointing away is never visible on a closed
    part. It is a cost decision, not a correctness one -- order_faces is
    O(faces^2) in witness tests and 3649 sews 846 of them.
    """
    out = []
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        if BRepAdaptor_Surface(face).GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        f = _plane_face(face, proj)
        if cull_back and f["normal"][2] > -1e-6:
            continue
        if len(f["poly"]) >= 3:
            out.append(f)
    return out
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k "flat_face or ring_face_carries or 32062_is_all or back_faces_are_culled" -v`
Expected: 5 passed

- [x] **Step 5: Mutate the cull guard and watch it fail**

Temporarily change `f["normal"][2] > -1e-6` to `f["normal"][2] > 1e6` (cull nothing), run the cull test, and confirm it fails on `len(kept) < len(every)`. Revert.

Run: `.venv/bin/pytest tests/test_occt.py -k back_faces_are_culled -v`
Expected while mutated: FAIL. Expected after revert: PASS.

- [x] **Step 6: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "build fill faces for the sewn shape's planes"
```

---

### Task 4: Return them, and fill a flat part

**Files:**
- Modify: `brick_icons/occt.py:896-943` (`visible_segments`)
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def test_visible_segments_returns_faces_and_a_projection(ldraw_dir):
    out = occt.flatten_part("32062", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert res.faces
    assert res.proj is not None


def test_a_flat_part_actually_fills_under_occt(tmp_path, ldraw_dir):
    """The whole point: flat3 emitted strokes and no fills for the life of
    the port, and nothing errored."""
    from brick_icons.cli import build_parser, _config_from_args, process_one
    args = build_parser().parse_args(
        ["32062", "--engine", "occt", "--format", "svg",
         "--shading", "outline", "--shade-style", "flat3",
         "--out", str(tmp_path)])
    process_one(_config_from_args(args), "32062", tmp_path)
    svg = (tmp_path / "32062.svg").read_text()
    assert svg.count("fill=\"#") > 1


def test_the_fit_sidecar_still_composes_under_occt(ldraw_dir):
    """occt's Projection has an identity pixel fit, so canvas_affine must
    still return the canvas fit unchanged -- the sidecar reads it."""
    out = occt.flatten_part("32062", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert hlr.canvas_affine(res, 3.0, 5.0, 7.0) == (3.0, 5.0, 7.0)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k "returns_faces_and_a_projection or actually_fills or fit_sidecar_still" -v`
Expected: FAIL — `assert res.faces` on an empty tuple.

- [x] **Step 3: Write the implementation**

In `visible_segments`, replace the final return with:

```python
    proj = op_projection(right, up, fwd)
    faces = plane_faces(shape, proj)
    return VisResult(ops, bbox, s, faces=faces, analytic=(),
                     ellipses=tuple(ells), proj=proj, sil_polys=polys)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k "returns_faces_and_a_projection or actually_fills or fit_sidecar_still" -v`
Expected: 3 passed

- [x] **Step 5: Look at it**

```bash
.venv/bin/python -m brick_icons.cli 32062 --engine occt --format svg \
  --shading outline --shade-style flat3 --out /tmp/occtfaces
resvg --background white --width 512 /tmp/occtfaces/32062.svg /tmp/occtfaces/32062.png
open /tmp/occtfaces/32062.png
```

Expected: a filled part, not an outline. Compare against the same command with `--engine naive`.

- [x] **Step 6: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "return the occt engine's flat fill faces"
```

---

### Task 5: The limb solver

A cylinder or cone's silhouette is a generator where the surface normal turns perpendicular to the view. Both surfaces have a normal of the form `cos u * a + sin u * b + c`, so one solver covers both.

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def test_a_cylinder_across_the_view_has_two_limbs_half_a_turn_apart():
    fwd = np.array([0.0, 0.0, 1.0])
    a, b, c = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.zeros(3)
    us = occt._limb_params(a, b, c, fwd)
    assert len(us) == 2
    assert abs(((us[1] - us[0]) % (2 * math.pi)) - math.pi) < 1e-9


def test_a_surface_that_never_turns_edge_on_has_no_limb():
    """A cone pointed at the camera: every normal leans toward it."""
    fwd = np.array([0.0, 0.0, 1.0])
    a = np.array([0.05, 0.0, 0.0]); b = np.array([0.0, 0.05, 0.0])
    c = np.array([0.0, 0.0, -1.0])
    assert occt._limb_params(a, b, c, fwd) == []


def test_a_limb_parameter_really_is_edge_on():
    fwd = np.array([0.3, -0.5, 0.81]); fwd = fwd / np.linalg.norm(fwd)
    a = np.array([1.0, 0.2, 0.0]); b = np.array([0.1, 1.0, 0.3])
    c = np.array([0.0, 0.0, 0.4])
    for u in occt._limb_params(a, b, c, fwd):
        n = math.cos(u) * a + math.sin(u) * b + c
        assert abs(float(n @ fwd)) < 1e-9
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k limb -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute '_limb_params'`

- [x] **Step 3: Write the implementation**

```python
def _limb_params(a, b, c, fwd):
    """Parameters where a curved surface turns edge-on to the camera.

    Every curved surface in this library has a normal of the form
    n(u) = cos u * a + sin u * b + c (c is zero for a cylinder, the axial term
    for a cone), so n(u).fwd = 0 is A cos u + B sin u + C = 0 -- at most two
    roots, and none when the surface never turns edge-on at all.
    """
    A, B, C = float(a @ fwd), float(b @ fwd), float(c @ fwd)
    R = math.hypot(A, B)
    if R < 1e-12:
        return []
    ratio = -C / R
    if abs(ratio) > 1.0:
        return []
    phi = math.atan2(A, B)              # A cos u + B sin u == R sin(u + phi)
    u = math.asin(max(-1.0, min(1.0, ratio)))
    return sorted({(u - phi) % (2 * math.pi),
                   (math.pi - u - phi) % (2 * math.pi)})
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k limb -v`
Expected: 3 passed

- [x] **Step 5: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "solve for a curved face's limb generators"
```

---

### Task 6: Curved faces as limb-cut spans

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def _curved_of(part, ldraw_dir, lat=30.0, long=45.0):
    out = occt.flatten_part(part, ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(lat, long)
    proj = occt.op_projection(right, up, fwd)
    return occt.curved_faces(shape, proj), proj


def test_a_cylinder_splits_into_spans_at_its_limbs(ldraw_dir):
    """3005 sews exactly one cylinder (its stud), and a stud seen from an
    iso view shows a front half and a back half."""
    faces, _ = _curved_of("3005", ldraw_dir)
    assert len(faces) == 2
    assert sum(1 for f in faces if f.get("interior")) == 1


def test_a_span_carries_the_gradient_fields_fill_ops_reads(ldraw_dir):
    faces, _ = _curved_of("4740", ldraw_dir)
    assert faces
    for f in faces:
        assert set(f) >= {"poly", "zs", "depth", "grad_axis", "grad_samples",
                          "span_deg", "color"}
        offs = [o for o, _ in f["grad_samples"]]
        assert offs == sorted(offs)
        assert all(0.0 <= o <= 1.0 for o in offs)


def test_a_span_boundary_lies_on_the_true_projected_ellipse(ldraw_dir):
    """The point of the exact route: boundary points sit ON the conic, so
    arc recovery reads the run back as an arc instead of a chord fan."""
    out = occt.flatten_part("3005", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    ax, ay = occt._screen_axes(right, up)
    cyl = [f for f in occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Cylinder)]
    surf = occt.BRepAdaptor_Surface(cyl[0]).Cylinder()
    o = surf.Position().Location()
    o = np.array([o.X(), o.Y(), o.Z()])
    xd, yd = surf.Position().XDirection(), surf.Position().YDirection()
    u = np.array([xd.X(), xd.Y(), xd.Z()]) * surf.Radius()
    v = np.array([yd.X(), yd.Y(), yd.Z()]) * surf.Radius()
    loc = occt._ell_locus(o, u, v, 1.0, 1.0, "sil", ax, ay)
    span = occt.curved_faces(shape, proj)[0]
    on = span["poly"].copy()
    on[:, 1] *= -1.0                     # back out of op space into locus space
    hits = sum(1 for p in on if occt._on_locus(p[None, :], loc))
    assert hits >= len(on) // 3          # the two arc runs, not the two limbs


def test_a_span_does_not_wrap_past_its_own_limb(ldraw_dir):
    faces, _ = _curved_of("3005", ldraw_dir)
    assert all(f["span_deg"] <= 180.0 + 1e-6 for f in faces)
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k "splits_into_spans or gradient_fields or true_projected_ellipse or wrap_past" -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute 'curved_faces'`

- [x] **Step 3: Write the implementation**

```python
def _faces_of_type(shape, want):
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        if BRepAdaptor_Surface(face).GetType() == want:
            yield face


def _curved_frame(face):
    """(point(u, v), normal(u), a, b, c) for a cylinder or cone face.

    `point` and `normal` are callables in the surface's own parameters;
    (a, b, c) are the normal's cos/sin/constant vectors for _limb_params.
    """
    s = BRepAdaptor_Surface(face)
    kind = s.GetType()
    g = s.Cylinder() if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder else s.Cone()
    pos = g.Position()
    o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
    X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
    Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
    Z = np.array([pos.Direction().X(), pos.Direction().Y(), pos.Direction().Z()])
    flip = -1.0 if face.Orientation() == TopAbs_Orientation.TopAbs_REVERSED else 1.0

    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        r = g.Radius()

        def point(u, v):
            u = np.atleast_1d(np.asarray(u, float))
            return (o + r * (np.cos(u)[:, None] * X + np.sin(u)[:, None] * Y)
                    + np.asarray(v, float).reshape(-1, 1) * Z)

        a, b, c = flip * X, flip * Y, np.zeros(3)
    else:
        r0, semi = g.RefRadius(), g.SemiAngle()

        def point(u, v):
            u = np.atleast_1d(np.asarray(u, float))
            v = np.asarray(v, float).reshape(-1, 1)
            rad = r0 + v * math.sin(semi)
            return (o + rad * (np.cos(u)[:, None] * X + np.sin(u)[:, None] * Y)
                    + v * math.cos(semi) * Z)

        a = flip * math.cos(semi) * X
        b = flip * math.cos(semi) * Y
        c = flip * -math.sin(semi) * Z

    def normal(u):
        return math.cos(u) * a + math.sin(u) * b + c

    return point, normal, a, b, c


def _span_face(point, normal, ua, ub, v0, v1, proj, step_deg=BOUNDARY_STEP_DEG):
    """One limb-to-limb span of a curved face, as a fill_ops face dict.

    Boundary order is top arc, limb generator, bottom arc, limb generator --
    the arcs sampled on the true circle, the generators straight because they
    are straight. Same field set as primitives._wall_span_face, which is what
    shade's gradient machinery reads.
    """
    n = max(2, int(math.ceil(abs(math.degrees(ub - ua)) / step_deg)) + 1)
    us = np.linspace(ua, ub, n)
    top = point(us, v1)
    bot = point(us, v0)
    tpx, tpy, tz = proj.to_px(top)
    bpx, bpy, bz = proj.to_px(bot)
    poly = np.concatenate([np.stack([tpx, tpy], 1),
                           np.stack([bpx, bpy], 1)[::-1]], axis=0)
    zs = np.concatenate([tz, bz])

    mid = point(np.array([ua, ub]), (v0 + v1) / 2.0)
    mpx, mpy, _ = proj.to_px(mid)
    p0 = (float(mpx[0]), float(mpy[0]))
    p1 = (float(mpx[1]), float(mpy[1]))
    axis = np.array([p1[0] - p0[0], p1[1] - p0[1]])
    L2 = float(axis @ axis) or 1.0
    samples = []
    for th in np.linspace(ua, ub, 9):
        nw = normal(th)
        nw = nw / np.linalg.norm(nw)
        nv = np.array([nw @ proj.right, nw @ proj.up, nw @ proj.fwd])
        p = point(np.array([th]), (v0 + v1) / 2.0)
        ppx, ppy, _ = proj.to_px(p)
        off = ((ppx[0] - p0[0]) * axis[0] + (ppy[0] - p0[1]) * axis[1]) / L2
        samples.append((float(np.clip(off, 0.0, 1.0)), nv))

    mid_n = normal((ua + ub) / 2.0)
    mid_n = mid_n / np.linalg.norm(mid_n)
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)),
            "kind": "occt-wall", "color": 16,
            # the far half of a wall: order_faces takes its depth from the
            # occluder's FAR hit, which is what `interior` selects
            "interior": bool(mid_n @ proj.fwd > 0),
            "span_deg": abs(math.degrees(ub - ua)),
            "grad_axis": (p0, p1), "grad_samples": samples}


def curved_faces(shape, proj, step_deg=BOUNDARY_STEP_DEG):
    """Cylinder and cone faces, cut at their limbs into spans."""
    out = []
    for want in (GeomAbs_SurfaceType.GeomAbs_Cylinder,
                 GeomAbs_SurfaceType.GeomAbs_Cone):
        for face in _faces_of_type(shape, want):
            point, normal, a, b, c = _curved_frame(face)
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
            cuts = [u for u in _limb_params(a, b, c, proj.fwd)
                    if u0 + 1e-9 < _unwrap(u, u0) < u1 - 1e-9]
            edges = sorted({u0, u1} | {_unwrap(u, u0) for u in cuts})
            for ua, ub in zip(edges, edges[1:]):
                if ub - ua < 1e-9:
                    continue
                f = _span_face(point, normal, ua, ub, v0, v1, proj, step_deg)
                if len(f["poly"]) >= 3:
                    out.append(f)
    return out


def _unwrap(u, u0):
    """`u` lifted into [u0, u0 + 2*pi) -- UV bounds are not always [0, 2*pi)."""
    return u0 + (u - u0) % (2 * math.pi)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_occt.py -k "splits_into_spans or gradient_fields or true_projected_ellipse or wrap_past" -v`
Expected: 4 passed

- [x] **Step 5: Wire them in and look**

In `visible_segments`, change the face line to:

```python
    faces = plane_faces(shape, proj) + curved_faces(shape, proj)
```

```bash
.venv/bin/python -m brick_icons.cli 4740 --engine occt --format svg \
  --shading outline --shade-style flat3 --out /tmp/occtfaces
resvg --background white --width 512 /tmp/occtfaces/4740.svg /tmp/occtfaces/4740.png
open /tmp/occtfaces/4740.png
```

Expected: the dish's walls carry a gradient, not a flat tone, and no band crosses a silhouette.

- [x] **Step 6: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "cut curved faces at their limbs into fill spans"
```

---

### Task 7: Exact depth, and the paint order

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

- [x] **Step 1: Write the failing tests**

```python
def test_a_cylinder_span_occluder_reports_the_surface_depth(ldraw_dir):
    """The reason this slice pulls migration item 2 in: a flat depth is
    wrong in the middle of the span, which is where it overlaps a neighbour."""
    out = occt.flatten_part("3005", ldraw_dir)
    shape = occt.build_shape(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = occt.op_projection(right, up, fwd)
    face = next(occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Cylinder))
    occ = occt._face_occluder(face)
    point, _, _, _, _ = occt._curved_frame(face)
    u0, u1, v0, v1 = occt.BRepTools.UVBounds_s(face)
    # the occluder reports the NEAREST hit, so probe the front-most point:
    # taking mid-u would land on the back half half the time and compare the
    # near surface against the far one
    us = np.linspace(u0, u1, 181)
    P = point(us, (v0 + v1) / 2.0)
    x, y, z = proj.to_px(P)
    i = int(np.argmin(z))
    d = occ.depth(proj.ray_origin(x[i:i + 1], y[i:i + 1]), proj.fwd)
    assert np.isfinite(d).all()
    assert abs(float(d[0]) - float(z[i])) < 1e-6


def test_a_flat_face_gets_no_occluder(ldraw_dir):
    """Its depth is affine, so _plane_depth_fn is already exact and an
    occluder would be a slower way to get the same number."""
    out = occt.flatten_part("32062", ldraw_dir)
    shape = occt.build_shape(out)
    face = next(occt._faces_of_type(shape, occt.GeomAbs_SurfaceType.GeomAbs_Plane))
    assert occt._face_occluder(face) is None


def test_faces_come_back_in_paint_order(ldraw_dir):
    out = occt.flatten_part("3005", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    assert all("order" in f for f in res.faces)
    assert [f["order"] for f in res.faces] == sorted(f["order"] for f in res.faces)


def test_the_stud_paints_over_the_top_face_it_sits_on(ldraw_dir):
    """A near surface ordering behind a far one is the failure this whole
    task exists to prevent, and it is invisible in a field-set check."""
    out = occt.flatten_part("3005", ldraw_dir)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    res = occt.visible_segments(out, right, up, 512, cull=True, fwd=fwd)
    walls = [f for f in res.faces if f["kind"] == "occt-wall"]
    flats = [f for f in res.faces if f["kind"] == "occt-plane"]
    assert walls and flats
    nearest_wall = min(walls, key=lambda f: f["depth"])
    nearest_flat = min(flats, key=lambda f: f["depth"])
    if nearest_wall["depth"] < nearest_flat["depth"]:
        assert nearest_wall["order"] > nearest_flat["order"]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_occt.py -k "occluder or paint_order or paints_over" -v`
Expected: FAIL, `AttributeError: module 'brick_icons.occt' has no attribute '_face_occluder'`

- [x] **Step 3: Write the implementation**

```python
def _face_occluder(face):
    """The exact surface behind a curved face, as one of the occluder classes
    the naive engine already probes along a witness ray.

    They take a LOCAL frame whose columns are (U, axis, V) with unit radius
    and height 0..1, so the frame is built to carry the face's own radius and
    height. A plane gets None: its depth is affine and _plane_depth_fn
    recovers it exactly.
    """
    s = BRepAdaptor_Surface(face)
    kind = s.GetType()
    if kind not in (GeomAbs_SurfaceType.GeomAbs_Cylinder,
                    GeomAbs_SurfaceType.GeomAbs_Cone):
        return None
    g = s.Cylinder() if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder else s.Cone()
    pos = g.Position()
    o = np.array([pos.Location().X(), pos.Location().Y(), pos.Location().Z()])
    X = np.array([pos.XDirection().X(), pos.XDirection().Y(), pos.XDirection().Z()])
    Y = np.array([pos.YDirection().X(), pos.YDirection().Y(), pos.YDirection().Z()])
    Z = np.array([pos.Direction().X(), pos.Direction().Y(), pos.Direction().Z()])
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    # the occluders measure their sector from local angle 0
    Xs = math.cos(u0) * X + math.sin(u0) * Y
    Ys = -math.sin(u0) * X + math.cos(u0) * Y
    sector = math.degrees(u1 - u0)
    h = v1 - v0

    if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
        r = g.Radius()
        R = np.column_stack([r * Xs, h * Z, r * Ys])
        return primitives.CylinderOccluder(R, o + v0 * Z, sector)

    semi = g.SemiAngle()
    rb = g.RefRadius() + v0 * math.sin(semi)
    rt = g.RefRadius() + v1 * math.sin(semi)
    if abs(rb - rt) < 1e-9:
        return None                      # degenerate cone: no exact taper
    # ConeOccluder is radius (top+1) at y=0 tapering to top at y=1
    scale = rb - rt
    top = rt / scale
    R = np.column_stack([scale * Xs, h * math.cos(semi) * Z, scale * Ys])
    return primitives.ConeOccluder(R, o + v0 * Z, sector, top)
```

and, in `visible_segments`, replace the face line with:

```python
    proj = op_projection(right, up, fwd)
    faces, own_occ = [], {}
    for face in _shape_faces(shape):
        occ = _face_occluder(face)
        for f in _faces_for(face, proj):
            faces.append(f)
            if occ is not None:
                own_occ[id(f)] = occ
    from . import shade
    zs = np.concatenate([f["zs"] for f in faces]) if faces else np.zeros(1)
    zrange = float(zs.max() - zs.min()) or 1.0
    faces = shade.order_faces(faces, proj, 1e-3 * zrange, own_occ=own_occ)
```

with the two helpers that replace `plane_faces` / `curved_faces`'s own traversal:

```python
def _shape_faces(shape):
    ex = TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        ex.Next()
        yield face


def _faces_for(face, proj, cull_back=True, step_deg=BOUNDARY_STEP_DEG):
    """Every fill face one OCCT face contributes: one for a plane, one per
    limb-cut span for a cylinder or cone."""
    kind = BRepAdaptor_Surface(face).GetType()
    if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
        f = _plane_face(face, proj, step_deg)
        if cull_back and f["normal"][2] > -1e-6:
            return []
        return [f] if len(f["poly"]) >= 3 else []
    if kind not in (GeomAbs_SurfaceType.GeomAbs_Cylinder,
                    GeomAbs_SurfaceType.GeomAbs_Cone):
        return []
    point, normal, a, b, c = _curved_frame(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    cuts = {_unwrap(u, u0) for u in _limb_params(a, b, c, proj.fwd)}
    edges = sorted({u0, u1} | {u for u in cuts if u0 + 1e-9 < u < u1 - 1e-9})
    out = []
    for ua, ub in zip(edges, edges[1:]):
        if ub - ua < 1e-9:
            continue
        f = _span_face(point, normal, ua, ub, v0, v1, proj, step_deg)
        if len(f["poly"]) >= 3:
            out.append(f)
    return out
```

Keep `plane_faces` and `curved_faces` as thin wrappers over `_faces_for` so the Task 3 and Task 6 tests still address them:

```python
def plane_faces(shape, proj, cull_back=True):
    return [f for face in _shape_faces(shape)
            for f in _faces_for(face, proj, cull_back=cull_back)
            if f["kind"] == "occt-plane"]


def curved_faces(shape, proj, step_deg=BOUNDARY_STEP_DEG):
    return [f for face in _shape_faces(shape)
            for f in _faces_for(face, proj, step_deg=step_deg)
            if f["kind"] == "occt-wall"]
```

- [x] **Step 4: Run the whole occt suite**

Run: `.venv/bin/pytest tests/test_occt.py -q`
Expected: all pass, 0 failed

- [x] **Step 5: Mutate the occluder and watch the depth test fail**

Temporarily return `None` from `_face_occluder` for cylinders. Run the depth test and confirm it fails; revert.

Run: `.venv/bin/pytest tests/test_occt.py -k occluder_reports_the_surface_depth -v`
Expected while mutated: FAIL. After revert: PASS.

- [x] **Step 6: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "order occt's faces by their own surfaces"
```

---

### Task 8: Measure parity on the combo where fills exist

`compare-engines.py` renders only the strokes-only `outline` combo, so it cannot see a fill.

**Files:**
- Modify: `scripts/compare-engines.py:36-42` (`load_outline_parts`) and its `main`
- Test: `tests/test_occt.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compare_engines_can_select_a_combo():
    spec = importlib.util.spec_from_file_location(
        "compare_engines", ROOT / "scripts" / "compare-engines.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parts, args = mod.load_combo_parts(
        ROOT / "tests" / "goldens" / "manifest.toml", "outline-flat3",
        "unprinted")
    assert "--shade-style" in args and "flat3" in args
    assert "3068bp00" not in parts          # printed parts stay out
    assert len(parts) == 21
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_occt.py -k compare_engines_can_select -v`
Expected: FAIL, `AttributeError: module 'compare_engines' has no attribute 'load_combo_parts'`

- [ ] **Step 3: Write the implementation**

Replace `load_outline_parts` in `scripts/compare-engines.py`:

```python
def load_combo_parts(manifest: Path, combo: str, parts_key: str | None = None):
    """(parts, args) for one manifest combo.

    `parts_key` overrides the combo's own part list -- `outline-flat3` names
    `all`, which carries printed parts, and a print is out of the engine loop
    until decal extraction reaches the render path.
    """
    cfg = tomllib.loads(manifest.read_text())
    spec = cfg["combo"][combo]
    names = parts_key or spec["parts"]
    parts = cfg["parts"][names] if isinstance(names, str) else names
    return parts, spec["args"]
```

and in `main`, add the arguments and use them:

```python
    ap.add_argument("--combo", default="outline",
                    help="manifest combo to render (outline, outline-flat3)")
    ap.add_argument("--parts", default=None,
                    help="manifest parts key to use instead of the combo's own")
```

```python
    parts, args = load_combo_parts(Path(a.manifest), a.combo, a.parts)
```

Update every remaining `load_outline_parts` call site the same way.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_occt.py -k compare_engines_can_select -v`
Expected: 1 passed

- [ ] **Step 5: Run the parity measurement**

```bash
.venv/bin/python scripts/compare-engines.py --combo outline-flat3 \
  --parts unprinted --out /tmp/engines-flat3.json
```

Expected: one progress line per part as it finishes (21 of them), then a summary. Read the fill palette and element counts naive against occt; a part whose occt fill count is 0 is a face producer failure, not a shading difference.

- [ ] **Step 6: Commit**

```bash
git add scripts/compare-engines.py tests/test_occt.py
git commit -m "compare the engines on the combo that has fills"
```

---

### Task 9: Verify the naive path did not move, and record the state

**Files:**
- Modify: `HANDOFF.md`
- Modify: `OCCT-MIGRATION.md`

- [ ] **Step 1: Run the full suite outside the goldens**

Run: `.venv/bin/pytest -q`
Expected: all pass. A bare run reports skips for the three drift tests — that is not verification, which is why the next step exists.

- [ ] **Step 2: Run the drift gate**

Run: `BRICK_GOLDENS=1 .venv/bin/pytest tests/test_goldens.py -q`
Expected: passes, 0 skipped. Nothing on the naive path changed, so `tests/goldens/hashes.txt` must be untouched — confirm with `git status tests/goldens/`, which must report no modification.

- [ ] **Step 3: Update the migration roadmap**

In `OCCT-MIGRATION.md`, replace the `## The blocker: occt.visible_segments returns faces=()` section with what is now true, and strike items 1 and 2 from `## Ordered work` — item 2 landed with item 1, deliberately. Leave items 3, 4 and 5 as they stand.

- [ ] **Step 4: Record the parity numbers**

In `HANDOFF.md`, add what `compare-engines.py --combo outline-flat3` reported: which parts fill, which diverge from naive and by how much. Numbers only, from the run in Task 8 — a claim about a part nobody rendered is the thing this file exists to prevent.

- [ ] **Step 5: Commit**

```bash
git add HANDOFF.md OCCT-MIGRATION.md
git commit -m "record what the occt engine's fills do on the corpus"
```

---

## Open, and worth revisiting

The exact-occluder depth (Task 7) was chosen over a flat depth per span without a measurement behind it. If it fights back — the occluder frame is fiddly to build from an OCCT surface, or the witness probe costs too much on 3649's 846 faces — the fallback is to drop `own_occ` and let `_plane_depth_fn` handle every span. Nothing else in this plan depends on which is in place.
