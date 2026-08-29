# OCCT Hidden-Line Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render visible edges through OCCT's exact hidden-line removal behind `--engine occt`, leaving the naive engine as the default.

**Architecture:** One new module, `brick_icons/occt.py`, is the only importer of `OCP`. `hlr.visible_segments` gains an `engine` parameter and dispatches after the shared `flatten` → `repair` front end, returning the same `VisResult` from either path. Everything downstream — `fit_segments`, `fit_affine`, `segments_to_svg` — is already engine-agnostic and is not touched.

**Tech Stack:** Python 3.14, `cadquery-ocp` 7.9.3 (OCCT 7.9.3 via pybind11), numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-occt-adoption-design.md`. Read it and the spike it cites (`docs/superpowers/specs/2026-08-29-occt-spike.md`, on branch `occt-spike`) before starting.

## Global Constraints

- `cadquery-ocp` is an **optional extra**, never a hard dependency. `pip install -e '.[occt]'`.
- `brick_icons/occt.py` is the **only** module that may `import OCP`.
- A part that fails to build **raises**. Never fall back to the naive engine — a silent fallback makes the gate report success for parts the kernel never touched.
- Scope is edges only. Do not touch `shapely`, `unwrap.py`, decal code, or `hlr.part_geometry`. Do not add fills.
- Segment ops are `("line", x1, y1, x2, y2, kind)` and `("arc", cx, cy, ux, uy, vx, vy, t0, t1, kind)`. `kind == "sil"` selects `--silhouette-width`; anything else gets `--line-width`.
- Work happens in the worktree `.claude/worktrees/occt-port` on branch `occt-port`. Do not run git against the shared checkout.
- Run tests with `.venv/bin/python -m pytest`.
- Installing the extra needs `PIP_CONFIG_FILE=/dev/null` — a global `extra-index-url` points at a private registry and prompts for auth, killing non-interactive installs.

---

### Task 1: Freeze the plain-outline gate

The corpus has no combo that tests occlusion without also testing fills. `--wireframe` sets `cull=False` and draws hidden geometry (`3001`: 46 paths vs plain outline's 26), so it cannot gate hidden-line removal.

**Files:**
- Modify: `tests/goldens/manifest.toml`
- Test: `tests/test_goldens.py`

**Interfaces:**
- Consumes: `brick_icons.goldens.summarize_svg`, `scripts/freeze-goldens.py`, `scripts/compare-goldens.py` (all on `main` as of `86cd5b2`).
- Produces: golden case ids `outline__<part>` under `tests/goldens/render/`, and rows in `tests/goldens/hashes.txt`.

**Status: the row landed externally.** The session that owns the corpus added
it and re-froze on `main`:

```toml
[combo.outline]
parts = "all"
args = ["--format", "svg", "--shading", "outline"]
```

`all` is 23 parts, not the 8-part `spread` — plain outline is cheap (no fill
computation) and an HLR swap is the highest-risk change in the tree, so the
coverage is worth the freeze time.

- [ ] **Step 1: Confirm the freeze landed and the pre-existing cases held**

Do not gate against `tests/goldens/` until the corpus owner confirms the 31
pre-existing cases are unmoved. If they moved, that is a bug in the freeze, not
in this port, and it must be settled first.

- [ ] **Step 2: Rebase this worktree onto the commit carrying the combo**

Run: `git -C . fetch . main && git rebase main`
Expected: `tests/goldens/render/outline__*.json` present, 23 of them.

- [ ] **Step 3: Verify the new cases carry no fills**

```python
def test_outline_combo_is_strokes_only():
    """The HLR gate must not also test the fill path.

    A fill entering these cases would make an engine swap answerable for
    shading too, which is a separate track (Skia PathOps, evaluated
    elsewhere).
    """
    import json, pathlib
    for p in pathlib.Path("tests/goldens/render").glob("outline__*.json"):
        fills = json.loads(p.read_text())["fills"]
        assert set(fills) <= {"none"}, f"{p.name} has fills: {fills}"
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/test_goldens.py -k outline_combo -v`
Expected: PASS.

- [ ] **Step 5: Confirm the baseline is reproducible**

Run: `.venv/bin/python scripts/compare-goldens.py`
Expected: zero deltas. The measured noise floor is exactly zero, so any nonzero result here is a real bug, not tolerance.

- [ ] **Step 6: Commit**

Stage `tests/goldens/manifest.toml`, `tests/goldens/render`, `tests/goldens/hashes.txt` and `tests/test_goldens.py`, with the message: `freeze a strokes-only outline combo as the hidden-line gate`

---

### Task 2: The `--engine` selector

**Files:**
- Modify: `pyproject.toml`
- Modify: `brick_icons/config.py` (`DEFAULTS`, the `Config` dataclass, and the `load_config` constructor call)
- Modify: `brick_icons/cli.py` (`_parse_args`, `_config_from_args`, `process_one`)
- Modify: `brick_icons/hlr.py` (`visible_segments`)
- Create: `brick_icons/occt.py`
- Test: `tests/test_config.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Config.engine: str` (`"naive"` default), CLI flag `--engine {naive,occt}`, and `hlr.visible_segments(part, ldraw_dir, lat, long, render_px, cull, engine="naive")`. Task 6 replaces the `NotImplementedError` this task installs.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
def test_engine_defaults_to_naive():
    assert load_config(root=".").engine == "naive"


def test_engine_override():
    assert load_config(root=".", overrides={"engine": "occt"}).engine == "occt"
```

```python
# tests/test_cli.py
def test_unknown_engine_is_rejected():
    with pytest.raises(SystemExit):
        cli._parse_args(["3001", "--engine", "raytrace"])
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -k engine tests/test_cli.py -k engine -v`
Expected: FAIL — `Config` has no attribute `engine`.

- [ ] **Step 3: Add the config key**

In `brick_icons/config.py`, add to `DEFAULTS` beside `"shading"`:

```python
    "engine": "naive",       # naive | occt  (occt needs the [occt] extra)
```

Add `engine: str` to the `Config` dataclass, and `engine=str(data["engine"]),` to the constructor call in `load_config`.

- [ ] **Step 4: Add the CLI flag**

In `_parse_args`:

```python
    p.add_argument("--engine", choices=["naive", "occt"], default=None,
                   help="geometry engine for outline/wireframe renders")
```

In `_config_from_args`'s `overrides` dict:

```python
        "engine": args.engine,
```

- [ ] **Step 5: Thread it through the engine seam**

In `hlr.visible_segments`, add `engine="naive"` to the signature and branch before the existing analytic/faceted dispatch:

```python
    if engine == "occt":
        from . import occt
        return occt.visible_segments(out, right, up, fwd, render_px, cull=cull)
    if out["analytic"] or out["fit_arcs"]:
```

Create `brick_icons/occt.py` containing only:

```python
"""OCCT-backed hidden-line removal. The only module that imports OCP."""
from __future__ import annotations

try:
    import OCP  # noqa: F401
except ImportError as e:                      # pragma: no cover
    raise ImportError(
        "--engine occt needs the OCCT extra: pip install -e '.[occt]'"
    ) from e


def visible_segments(out, right, up, fwd, render_px, cull=True):
    raise NotImplementedError("OCCT engine lands in Task 6")
```

The guard is why `hlr.visible_segments` imports this module *inside* the
`engine == "occt"` branch rather than at file scope: a top-level import would
make the whole package unimportable without the extra.

In `cli.process_one`, pass `engine=cfg.engine` to the `hlr.visible_segments` call.

- [ ] **Step 6: Declare the optional extra**

In `pyproject.toml`:

```toml
[project.optional-dependencies]
occt = ["cadquery-ocp>=7.9.3"]
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_cli.py -v`
Expected: PASS, and no existing test regresses — `engine` defaults to `"naive"`, so every current invocation is unchanged.

- [ ] **Step 8: Commit**

Stage `pyproject.toml`, `brick_icons/config.py`, `brick_icons/cli.py`, `brick_icons/hlr.py`, `brick_icons/occt.py`, `tests/test_config.py`, `tests/test_cli.py`, with the message: `add an engine selector defaulting to the naive engine`

---

### Task 3: Build OCCT geometry from recognized primitives

Lifted from `scripts/spike-occt.py` on branch `occt-spike`, which is proven across 48 parts with zero build exceptions. Read it first: `git show occt-spike:scripts/spike-occt.py`.

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py` (create)

**Interfaces:**
- Consumes: `Config.engine` from Task 2. Primitive records from `hlr.flatten` — each has `.kind` (`"cyli"`, `"con"`, `"disc"`, `"ring"`, `"edge"`), `.R` (3x3), `.t` (3-vector), `.sector` (degrees), and `.top` / `.inner` (integer N for cones and rings).
- Produces: `occt.frame(prim)`, `occt.cone_radii(prim) -> (r_base, r_top)`, `occt.occt_faces(prim) -> list`, `occt.build_shape(out) -> TopoDS_Shape`, `occt.count_faces(shape) -> int`, `occt.flatten_part(part, ldraw_dir) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pytest

occt = pytest.importorskip("brick_icons.occt", reason="needs the [occt] extra")


class P:
    """Minimal stand-in for a recognized primitive."""
    def __init__(self, kind, R, t, sector=360.0, top=1, inner=1):
        self.kind, self.R, self.t = kind, R, t
        self.sector, self.top, self.inner = sector, top, inner


def test_sheared_frame_is_rejected():
    """Non-orthogonal frames have no exact OCCT counterpart (5% of parts)."""
    R = np.array([[1.0, 0.3, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert occt.frame(P("cyli", R, np.zeros(3))) is None


def test_cone_radii_are_n_plus_one_and_n_scaled():
    """conN is radius N+1 at the base tapering to N, BOTH in primitive units,
    so the matrix scale multiplies both. Using the scale directly as the outer
    radius builds a plausible-looking part at the wrong size."""
    prim = P("con", np.diag([2.0, 5.0, 2.0]), np.zeros(3), top=3)
    r_base, r_top = occt.cone_radii(prim)
    assert r_base == pytest.approx(8.0)   # (3 + 1) * 2
    assert r_top == pytest.approx(6.0)    # 3 * 2


def test_edge_primitives_contribute_no_surface():
    assert occt.occt_faces(P("edge", np.eye(3), np.zeros(3))) == []


def test_3001_builds_and_sews(ldraw_dir):
    """The spike's step 2: a real brick builds with no exceptions."""
    shape = occt.build_shape(occt.flatten_part("3001", ldraw_dir))
    assert occt.count_faces(shape) > 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occt.py -v`
Expected: SKIPPED if the extra is absent, otherwise FAIL with missing attributes. Install with `PIP_CONFIG_FILE=/dev/null .venv/bin/pip install cadquery-ocp`.

- [ ] **Step 3: Port the builder**

Copy `frame`, `ax2`, `sector_rad`, `sector_face`, `annulus_face`, `occt_faces` and `tri_face` from `scripts/spike-occt.py`, plus the sewing half of its `build`. Drop the `stats` counters — probe instrumentation. Add `cone_radii`, `count_faces` and `flatten_part` as named helpers so the tests can reach them.

The extrusion-direction trap is load-bearing and its comment must survive the copy:

```python
    # The axis sets the EXTRUSION direction, so it must always be +ah --
    # negating it to fix a left-handed sector sweep builds the cone/cylinder
    # backwards off its base plane, which reads as a gap between subparts.
    # Handle the sweep by starting the x-direction at -ang instead.
    zdir = ah
    if not rh:
        uh = math.cos(-ang) * np.asarray(uh, float) + math.sin(-ang) * np.cross(ah, uh)
```

`build_shape(out)` sews every primitive face plus a `tri_face` per leftover triangle with `BRepBuilderAPI_Sewing(1e-3)`, then runs `ShapeUpgrade_UnifySameDomain`. Sewing tolerance is irrelevant between 1e-4 and 1e-1 — shell counts do not move — so do not spend time tuning it.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_occt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Stage `brick_icons/occt.py` and `tests/test_occt.py`, with the message: `build exact OCCT geometry from recognized primitives`

---

### Task 4: Hidden-line removal and the projector frame

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

**Interfaces:**
- Consumes: `occt.build_shape` from Task 3.
- Produces: `occt.projector_axes(right, up) -> (z, x)` and `occt.hlr_edges(shape, right, up, fwd, cull=True) -> dict` keyed `"sharp"`, `"smooth"`, `"outline"`, each a `TopoDS_Compound` or `None`. With `cull=False` the dict also carries `"sharp_hidden"`, `"smooth_hidden"`, `"outline_hidden"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_projector_axis_puts_image_y_on_up():
    """OCCT derives image Y as Z x X. Feeding view_basis's `fwd` and `right`
    directly pitches the whole render 90 degrees."""
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    z, x = occt.projector_axes(right, up)
    assert np.allclose(np.cross(z, x), up, atol=1e-9)


@pytest.mark.xfail(reason="needs Task 6's render path", strict=False)
def test_orientation_is_verified_against_a_chiral_part(ldraw_dir, tmp_path):
    """A 180-degree 'rotation' that appears to fix orientation is a
    reflection: it measured RMSE 0.003 against the MIRROR of the render and
    0.344 against the render itself. Symmetric parts (brick, cone, round
    brick) cannot reveal this -- it took a gear's spokes. Hence 4019, and a
    comparison against the naive engine rather than against its own mirror.
    """
    naive = render_svg("4019", engine="naive", out=tmp_path / "n")
    ported = render_svg("4019", engine="occt", out=tmp_path / "o")
    assert rmse(ported, naive) < rmse(ported, mirrored(naive))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occt.py -k "projector or chiral" -v`
Expected: FAIL — `projector_axes` not defined.

- [ ] **Step 3: Implement**

```python
def projector_axes(right, up):
    """OCCT sets image Y = Z x X, so pick Z = right x up to land Y on `up`."""
    return np.cross(right, up), -np.asarray(right, float)


def hlr_edges(shape, right, up, fwd, cull=True):
    z, x = projector_axes(right, up)
    a = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*map(float, z)), gp_Dir(*map(float, x)))
    algo = HLRBRep_Algo()
    algo.Add(shape)
    algo.Projector(HLRAlgo_Projector(a))
    algo.Update()
    algo.Hide()
    hs = HLRBRep_HLRToShape(algo)
    wanted = [("sharp", hs.VCompound), ("smooth", hs.Rg1LineVCompound),
              ("outline", hs.OutLineVCompound)]
    if not cull:
        wanted += [("sharp_hidden", hs.HCompound),
                   ("smooth_hidden", hs.Rg1LineHCompound),
                   ("outline_hidden", hs.OutLineHCompound)]
    got = {}
    for name, fn in wanted:
        try:
            got[name] = fn()
        except Exception:
            got[name] = None
    return got
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_occt.py -v`
Expected: PASS, with the chirality test still xfail until Task 6.

- [ ] **Step 5: Commit**

Stage `brick_icons/occt.py` and `tests/test_occt.py`, with the message: `run exact hidden-line removal with a correctly framed projector`

---

### Task 5: Read curves off edges instead of refitting

This is the component that makes `arcfit.py` redundant. If arcs come out wrong, look here first.

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

**Interfaces:**
- Consumes: `occt.hlr_edges` from Task 4.
- Produces: `occt.edges_to_ops(compounds) -> list` of segment ops in model space — `("line", x1, y1, x2, y2, kind)` and `("arc", cx, cy, ux, uy, vx, vy, t0, t1, kind)`, where `kind` is `"sil"` for edges from any `outline*` compound and `"line"` otherwise.

- [ ] **Step 1: Write the failing tests**

```python
def test_circle_edges_become_arc_ops_not_polylines():
    """The whole point of the port: a projected stud rim arrives as a curve,
    so nothing has to guess a circle back out of a chord polygon."""
    shape = occt.build_shape(occt.flatten_part("3941", ldraw_dir))
    ops = occt.edges_to_ops(occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0)))
    assert any(op[0] == "arc" for op in ops)


def test_outline_compound_edges_are_silhouette_kind():
    """`kind == 'sil'` selects --silhouette-width downstream. The kernel
    reports the sharp/smooth/silhouette split directly, so this is kernel
    output rather than the inference the naive engine does."""
    shape = occt.build_shape(occt.flatten_part("3941", ldraw_dir))
    edges = occt.hlr_edges(shape, *hlr.view_basis(30.0, 45.0))
    ops = occt.edges_to_ops({"outline": edges["outline"]})
    assert ops and all(op[-1] == "sil" for op in ops)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_occt.py -k "arc_ops or silhouette" -v`
Expected: FAIL — `edges_to_ops` not defined.

- [ ] **Step 3: Implement**

Walk each compound with `TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)`. For each edge take `BRepAdaptor_Curve(edge)` and switch on `.GetType()`:

```python
def edges_to_ops(compounds):
    ops = []
    for name, comp in compounds.items():
        if comp is None:
            continue
        kind = "sil" if name.startswith("outline") else "line"
        ex = TopExp_Explorer(comp, TopAbs_ShapeEnum.TopAbs_EDGE)
        while ex.More():
            ops += _edge_ops(TopoDS.Edge_s(ex.Current()), kind)
            ex.Next()
    return ops


def _edge_ops(edge, kind):
    c = BRepAdaptor_Curve(edge)
    t0, t1 = c.FirstParameter(), c.LastParameter()
    t = c.GetType()
    if t == GeomAbs_CurveType.GeomAbs_Line:
        p, q = c.Value(t0), c.Value(t1)
        return [("line", p.X(), p.Y(), q.X(), q.Y(), kind)]
    if t == GeomAbs_CurveType.GeomAbs_Circle:
        g = c.Circle()
        r_maj = r_min = g.Radius()
    elif t == GeomAbs_CurveType.GeomAbs_Ellipse:
        g = c.Ellipse()
        r_maj, r_min = g.MajorRadius(), g.MinorRadius()
    else:
        # Nothing else should reach here after HLR, but a BSpline would:
        # discretize rather than drop the edge silently.
        d = GCPnts_QuasiUniformDeflection(c, 0.05)
        pts = [c.Value(d.Parameter(i + 1)) for i in range(d.NbPoints())]
        return [("line", a.X(), a.Y(), b.X(), b.Y(), kind)
                for a, b in zip(pts, pts[1:])]
    ctr = g.Location()
    ax = g.Position()
    u, v = ax.XDirection(), ax.YDirection()
    return [("arc", ctr.X(), ctr.Y(),
             u.X() * r_maj, u.Y() * r_maj, v.X() * r_min, v.Y() * r_min,
             t0, t1, kind)]
```

The projection drops Z, so `X()`/`Y()` are already image-space — HLR returns its
result in the projector's plane.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_occt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Stage `brick_icons/occt.py` and `tests/test_occt.py`, with the message: `read circles and ellipses off HLR edges instead of refitting`

---

### Task 6: Wire the engine into `visible_segments`

**Files:**
- Modify: `brick_icons/occt.py`
- Test: `tests/test_occt.py`

**Interfaces:**
- Consumes: `build_shape`, `hlr_edges`, `edges_to_ops`.
- Produces: `occt.visible_segments(out, right, up, fwd, render_px, cull=True) -> hlr.VisResult`, replacing the Task 2 stub. Fields set: `segs`, `bbox`, `s`. Every other field keeps its namedtuple default.

- [ ] **Step 1: Write the failing test**

```python
def test_3001_renders_through_the_occt_engine(tmp_path):
    cfg = load_config(toml_path="labels.toml", root=".",
                      overrides={"fmt": "svg", "shading": "outline",
                                 "engine": "occt"})
    process_one(cfg, "3001", tmp_path)
    s = goldens.summarize_svg((tmp_path / "3001.svg").read_text())
    assert s["paths"] > 0
    assert s["fills"] == {"none": s["paths"]}    # strokes only, no fills
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_occt.py -k renders_through -v`
Expected: FAIL with `NotImplementedError: OCCT engine lands in Task 6`.

- [ ] **Step 3: Implement**

```python
def visible_segments(out, right, up, fwd, render_px, cull=True):
    from .hlr import VisResult, _ops_bbox
    shape = build_shape(out)
    ops = edges_to_ops(hlr_edges(shape, right, up, fwd, cull=cull))
    if not ops:
        raise RuntimeError("OCCT engine produced no edges")
    bbox = _ops_bbox(ops)
    span = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) or 1.0
    s = (render_px - 20) / span
    return VisResult(ops, bbox, s)
```

`s` matches how the naive engine derives it in both `_visible_segments_faceted` and `_visible_segments_analytic`; `--scale-mode physical` depends on the two agreeing.

- [ ] **Step 4: Run the tests and drop Task 4's xfail**

Run: `.venv/bin/python -m pytest tests/test_occt.py -v`
Expected: PASS, including the chirality test once its `xfail` marker is removed.

- [ ] **Step 5: Render a part and look at it**

Run: `.venv/bin/python -m brick_icons.cli 3001 --format svg --shading outline --engine occt --out /tmp/occt` then `open /tmp/occt/3001.svg`
Expected: a brick with the right silhouette, the right stud count, and no interior geometry showing through. Repeat for `4589` and `3941` — the three the spike verified by eye. A coverage number is not evidence: `BOPAlgo_MakerVolume` scored `3649` at 55% area, which reads as partial success, while the render showed the gear's entire body missing.

- [ ] **Step 6: Commit**

Stage `brick_icons/occt.py` and `tests/test_occt.py`, with the message: `render visible segments through the OCCT engine`

---

### Task 7: Run the gate and record what moved

**Files:**
- Create: `scripts/compare-engines.py`
- Modify: `docs/superpowers/specs/2026-08-29-occt-adoption-design.md` (the `## Open` section)

**Interfaces:**
- Consumes: `occt.visible_segments`, `goldens.summarize_svg`, the frozen `outline__*` cases from Task 1.
- Produces: a per-part table of summary deltas between the two engines.

- [ ] **Step 1: Write the comparison script**

It renders each `outline` case under both engines and prints one line per part as it completes — `7/23 3941  A 12->28  L 96->40  bbox ok` — because the run takes minutes and a silent tool is indistinguishable from a hung one. Write results with `--out`; do not pipe through `tail`, which buffers everything until exit and destroys the stream.

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/compare-engines.py --out /tmp/engines.json`
Expected: one line per part, no exceptions.

- [ ] **Step 3: Read the result against the success criteria**

Success is not byte-identity. `bbox`, `viewBox` and the fill palette hold still; `A` rises and `L` falls on round parts. **A round part whose `A` count does not move is the suspicious one** — it means arcs are still arriving as chord polylines.

Check specifically:
- `4019`'s stray ellipse (radii 83.79 x 51.31, bbox y-min -11.08 against a `0 0 256 170` viewBox). Predicted to disappear, since it is an arc-recovery artifact and arc recovery is what goes away. A prediction, not a promise — record what actually happened.
- Any part whose bbox leaves its own viewBox. `test_drawings_stay_inside_their_own_viewbox` already checks this across the corpus with no baseline needed.

- [ ] **Step 4: Record the findings in the design doc**

Replace the two bullets under `## Open` with what the run measured. Sequential findings replace, they do not accumulate — edit the claim rather than appending a dated note beside it.

- [ ] **Step 5: Commit**

Stage `scripts/compare-engines.py` and the design doc, with the message: `compare engines across the outline corpus and record the deltas`

---

## Not in this plan

Fills and `--shade-style`, replacing `shapely`, decal carrier binding via `ShapeAnalysis_Surface`, deleting `arcfit.py`, and extracting an `engines/` protocol. Each needs its own plan.

Skia PathOps is **downstream of this port, not competing with it**: its booleans preserve conics exactly but never invent them — polyline in, polyline out. So it can only pay off once something upstream emits real curves, which is what this slice does. See `docs/superpowers/specs/2026-08-29-pathops-evaluation.md` on `main`.

`arcfit` in particular may not be removable at all: hand-faceted rounds are condline-marked triangle chains rather than primitives, so the kernel has no exact curve to report for them. Task 7's run is the first real evidence either way.
