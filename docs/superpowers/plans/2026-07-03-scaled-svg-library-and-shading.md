# Scaled SVG Library + Parameterized Shading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add physical-scale SVG output, a pluggable interior-shading system (flat 3-tone first), optional diffuse highlights, and a filtered/resumable library generator to the pure-Python `outline` renderer.

**Architecture:** All work is in the `outline` path (`hlr.py` / `primitives.py` / `trace.py` / `cli.py` / `config.py`), plus a new `shade.py` (faces + shading styles) and `library.py` (batch generator). Fills are computed as flat polygons in the same px-space as the outline strokes, composited back-to-front (painter's algorithm), with the crisp analytic strokes drawn on top. Physical scale is derived from the LDU→px factor `s` (1 LDU = 0.4 mm). LDView paths are untouched.

**Tech Stack:** Python 3.14, NumPy, Pillow, pytest, potrace (unused by these features). Spec: `docs/superpowers/specs/2026-07-03-scaled-svg-library-and-shading-design.md`.

---

## Phase 1 — Physical scale (SVG)

### Task 1: Surface the LDU→px factor `s` from the segment pipeline

**Files:**
- Modify: `brick_icons/hlr.py` (`_visible_segments_analytic`, `_visible_segments_faceted`, `visible_segments`)
- Test: `tests/test_hlr.py`

**Stable return shape:** to avoid the return arity growing across tasks (which would break earlier tests), `visible_segments` returns a `namedtuple VisResult(segs, bbox, s, faces, analytic, highlights)` from the START. `faces`, `analytic`, and `highlights` are empty lists until Phase 2/3 populate them. Callers use attribute access (`res.segs`, `res.s`), never positional unpacking.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hlr.py  (add)
def test_visible_segments_returns_scale_factor():
    from brick_icons import hlr
    res = hlr.visible_segments("3005", "vendor/ldraw", render_px=400)
    assert res.s > 0
    assert res.faces == [] and res.analytic == [] and res.highlights == []
    # 3005 is a 1x1 brick: footprint 20 LDU. bbox px width / s is a few tens of LDU.
    bx0, by0, bx1, by1 = res.bbox
    ldu_w = (bx1 - bx0) / res.s
    assert 10 < ldu_w < 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hlr.py::test_visible_segments_returns_scale_factor -v`
Expected: FAIL — `AttributeError: 'tuple' object has no attribute 's'`.

- [ ] **Step 3: Introduce `VisResult` and return it from all three functions**

At the top of `hlr.py` (after imports) add:

```python
from collections import namedtuple

VisResult = namedtuple("VisResult", "segs bbox s faces analytic highlights")
```

In `_visible_segments_faceted`, change the early-return empty case and final return:

```python
    if len(fitpts) == 0:
        return VisResult([], (0.0, 0.0, 1.0, 1.0), 1.0, [], [], [])
```
```python
    return VisResult(segs, (min(xs), min(ys), max(xs), max(ys)), s, [], [], [])
```

In `_visible_segments_analytic`, change its final `return segs, _ops_bbox(segs)` to:

```python
    return VisResult(segs, _ops_bbox(segs), s, [], [], [])
```

(`visible_segments` itself is unchanged — it already returns whatever the inner function returns.)

- [ ] **Step 4: Update the existing caller in `cli.py` so nothing breaks**

In `brick_icons/cli.py::process_one`, the outline branch currently unpacks:

```python
        segs, bbox = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                          render_px=cfg.render_px)
```

Change to attribute access:

```python
        res = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                   render_px=cfg.render_px)
        segs, bbox, s = res.segs, res.bbox, res.s
```

(`s` is unused for now; Task 4 uses it. `res.faces`/`res.analytic`/`res.highlights` are used in Tasks 9–10.)

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_hlr.py tests/test_cli.py -v`
Expected: PASS (all, including the new test).

- [ ] **Step 6: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py brick_icons/cli.py
git commit -m "feat(hlr): surface LDU->px scale from visible_segments"
```

---

### Task 2: Factor the fit affine out of `fit_segments`

**Files:**
- Modify: `brick_icons/hlr.py` (`fit_segments`)
- Test: `tests/test_hlr.py`

Rationale: shading fills (Phase 2) must use the exact same affine as the strokes so fills align with edges. Extract `(f, ox, oy)` computation into `fit_affine`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hlr.py  (add)
def test_fit_affine_matches_fit_segments():
    from brick_icons import hlr
    bbox = (0.0, 0.0, 100.0, 50.0)
    f, ox, oy = hlr.fit_affine(bbox, W=256, H=170, margin=6, scale=1.0)
    seg = ("line", 0.0, 0.0, 100.0, 50.0, "edge")
    out = hlr.fit_segments([seg], bbox, 256, 170, 6, 1.0)[0]
    assert out[1] == 0.0 * f + ox and out[2] == 0.0 * f + oy
    assert abs(out[3] - (100.0 * f + ox)) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hlr.py::test_fit_affine_matches_fit_segments -v`
Expected: FAIL — `AttributeError: module 'brick_icons.hlr' has no attribute 'fit_affine'`.

- [ ] **Step 3: Extract `fit_affine` and call it from `fit_segments`**

Add before `fit_segments`:

```python
def fit_affine(bbox, W, H, margin=6, scale=1.0):
    """Uniform scale+offset mapping the segment bbox into a W x H canvas."""
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    return f, ox, oy
```

Replace the head of `fit_segments` (the scale/bbox/f/ox/oy block) with:

```python
def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    f, ox, oy = fit_affine(bbox, W, H, margin, scale)
    out = []
```

(Leave the rest of `fit_segments` — the per-op loop — unchanged.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "refactor(hlr): extract fit_affine from fit_segments"
```

---

### Task 3: Physical-size SVG output in `trace.segments_to_svg`

**Files:**
- Modify: `brick_icons/trace.py` (`segments_to_svg`)
- Test: `tests/test_trace.py`

**Design:** In physical mode the caller passes `physical=(w_mm, h_mm)` and `s` (LDU→px). The `viewBox` stays in px units (`0 0 W H`), but the SVG root gets `width="{w_mm}mm" height="{h_mm}mm"`. Strokes are given in mm and converted to px: `stroke_px = mm / 0.4 * s`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trace.py  (add)
def test_segments_to_svg_physical_mm(tmp_path):
    segs = [("line", 10.0, 10.0, 90.0, 10.0, "edge")]
    out = _trace.segments_to_svg(
        segs, 100, 100, tmp_path / "p.svg",
        physical=(12.8, 9.6), s=5.0, line_mm=0.2, sil_mm=0.3)
    txt = out.read_text()
    assert 'width="12.8mm"' in txt and 'height="9.6mm"' in txt
    assert 'viewBox="0 0 100 100"' in txt
    # line stroke: 0.2mm / 0.4 * 5.0 = 2.5 px
    assert 'stroke-width="2.50"' in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_trace.py::test_segments_to_svg_physical_mm -v`
Expected: FAIL — `TypeError: segments_to_svg() got an unexpected keyword argument 'physical'`.

- [ ] **Step 3: Add physical params to `segments_to_svg`**

Replace the signature and header of `segments_to_svg`:

```python
def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=3,
                    physical=None, s=None, line_mm=0.2, sil_mm=0.3) -> Path:
    if physical is not None:
        w_mm, h_mm = physical
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{w_mm:.2f}mm" height="{h_mm:.2f}mm" '
                f'viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">')
        line_px = line_mm / 0.4 * s
        sil_px = sil_mm / 0.4 * s
    else:
        root = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
                f'preserveAspectRatio="xMidYMid meet">')
    parts = [root,
             '<rect width="100%" height="100%" fill="white"/>',
             '<g stroke="black" fill="none" stroke-linecap="round">']
```

(The rest of the function — the `for op in segs` loop and closing tags — is unchanged; `line_px`/`sil_px` are already formatted with `{sw}` — change those two format specs to `{sw:.2f}` so `2.5` renders as `2.50`: the two `stroke-width="{sw}"` become `stroke-width="{sw:.2f}"`.)

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_trace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/trace.py tests/test_trace.py
git commit -m "feat(trace): physical-mm SVG output with mm stroke widths"
```

---

### Task 4: Config + CLI wiring for `scale_mode` and mm strokes; use in `process_one`

**Files:**
- Modify: `brick_icons/config.py` (DEFAULTS, Config, load_config)
- Modify: `brick_icons/cli.py` (`_parse_args`, `_config_from_args`, `process_one`)
- Test: `tests/test_config.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py  (add)
def test_scale_mode_default_and_override(tmp_path):
    from brick_icons.config import load_config
    cfg = load_config(toml_path=None, overrides={}, root=".")
    assert cfg.scale_mode == "fit"
    assert cfg.line_mm == 0.2 and cfg.silhouette_mm == 0.3
    cfg2 = load_config(toml_path=None, overrides={"scale_mode": "physical"}, root=".")
    assert cfg2.scale_mode == "physical"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_scale_mode_default_and_override -v`
Expected: FAIL — `AttributeError: 'Config' object has no attribute 'scale_mode'`.

- [ ] **Step 3: Add config fields**

In `config.py` `DEFAULTS`, add:

```python
    "scale_mode": "fit",     # fit | physical  (physical: SVG sized in mm)
    "line_mm": 0.2,          # physical interior stroke width (mm)
    "silhouette_mm": 0.3,    # physical contour stroke width (mm)
```

In the `Config` dataclass, add:

```python
    scale_mode: str
    line_mm: float
    silhouette_mm: float
```

In `load_config`'s `Config(...)` construction, add:

```python
        scale_mode=str(data["scale_mode"]),
        line_mm=float(data["line_mm"]),
        silhouette_mm=float(data["silhouette_mm"]),
```

- [ ] **Step 4: Add CLI flags**

In `cli.py::_parse_args`, add:

```python
    p.add_argument("--scale-mode", dest="scale_mode", choices=["fit", "physical"])
    p.add_argument("--line-mm", dest="line_mm", type=float)
    p.add_argument("--silhouette-mm", dest="silhouette_mm", type=float)
```

In `_config_from_args`'s `overrides` dict, add:

```python
        "scale_mode": args.scale_mode, "line_mm": args.line_mm,
        "silhouette_mm": args.silhouette_mm,
```

- [ ] **Step 5: Use `scale_mode` in `process_one` (SVG branch only)**

In the outline SVG branch, replace:

```python
        if cfg.fmt in ("svg", "both"):
            fit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
            trace.segments_to_svg(fit, cfg.width, cfg.height, out_dir / f"{name}.svg",
                                  line_px=cfg.line_width, sil_px=cfg.silhouette_width)
```

with:

```python
        if cfg.fmt in ("svg", "both"):
            if cfg.scale_mode == "physical":
                bx0, by0, bx1, by1 = bbox
                pad_ldu = cfg.margin / cfg.render_px * 100  # small margin in LDU
                vb_w = (bx1 - bx0) + 2 * pad_ldu * s
                vb_h = (by1 - by0) + 2 * pad_ldu * s
                # shift segments so bbox+pad starts at origin of the viewBox
                shifted = hlr.fit_segments(
                    segs, (bx0 - pad_ldu * s, by0 - pad_ldu * s,
                           bx1 + pad_ldu * s, by1 + pad_ldu * s),
                    round(vb_w), round(vb_h), margin=0, scale=1.0)
                w_mm = vb_w / s * 0.4
                h_mm = vb_h / s * 0.4
                trace.segments_to_svg(
                    shifted, round(vb_w), round(vb_h), out_dir / f"{name}.svg",
                    physical=(w_mm, h_mm), s=s,
                    line_mm=cfg.line_mm, sil_mm=cfg.silhouette_mm)
            else:
                fit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                trace.segments_to_svg(fit, cfg.width, cfg.height, out_dir / f"{name}.svg",
                                      line_px=cfg.line_width, sil_px=cfg.silhouette_width)
```

- [ ] **Step 6: Write an end-to-end CLI test for physical sizing**

```python
# tests/test_cli.py  (add)
def test_physical_svg_scales_with_part(tmp_path):
    import re
    from brick_icons import cli
    def mm(part):
        cli.main([part, "--format", "svg", "--shading", "outline",
                  "--scale-mode", "physical", "--out", str(tmp_path)])
        txt = (tmp_path / f"{part}.svg").read_text()
        w = float(re.search(r'width="([\d.]+)mm"', txt).group(1))
        return w
    w_1x1 = mm("3005")   # 1x1 brick
    w_2x4 = mm("3001")   # 2x4 brick
    assert w_2x4 > w_1x1 * 1.5   # 2x4 is substantially wider than 1x1
```

(If `cli.main` needs a specific entry name, check the bottom of `cli.py`; use the module's documented entry — `cli.main(argv)`.)

- [ ] **Step 7: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brick_icons/config.py brick_icons/cli.py tests/test_config.py tests/test_cli.py
git commit -m "feat(cli): scale_mode=physical emits real-world-sized SVGs"
```

---

## Phase 2 — Shading (faces + painter + flat3)

### Task 5: `shade.py` — faces from faceted triangles (front-facing, with normal + depth)

**Files:**
- Create: `brick_icons/shade.py`
- Test: `tests/test_shade.py`

**A `Face` is:** `{"poly": np.ndarray (N,2) px-space points, "normal": np.ndarray (3,) view-space unit normal, "depth": float}`. Depth is the centroid's camera depth (larger = farther). Back-facing triangles (normal pointing away from camera) are culled.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shade.py  (new file)
import numpy as np
from brick_icons import shade, hlr


def test_faces_from_tris_culls_back_and_projects():
    # a single CCW triangle in the z=0 plane (LDraw world), facing -Z
    tri = np.array([[[0, 0, 0], [10, 0, 0], [0, 10, 0]]], float)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0.0, cy=0.0, half=50.0)
    # exactly one face survives iff it is front-facing; assert shape when present
    for f in faces:
        assert f["poly"].shape == (3, 2)
        assert abs(np.linalg.norm(f["normal"]) - 1.0) < 1e-6
        assert np.isfinite(f["depth"])
    assert len(faces) in (0, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py::test_faces_from_tris_culls_back_and_projects -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.shade'`.

- [ ] **Step 3: Implement `faces_from_tris`**

```python
# brick_icons/shade.py  (new file)
from __future__ import annotations

import math
import numpy as np

from . import hlr


def _project_px(P, right, up, fwd, s, cx, cy, half):
    a, b, z = hlr.project(P, right, up, fwd)
    return (a - cx) * s + half, (b - cy) * s + half, z


def faces_from_tris(tri, right, up, fwd, s, cx, cy, half):
    """Front-facing triangle faces as px-space polygons with view-space normals."""
    faces = []
    for v in tri:                       # v: (3,3) world coords
        n = np.cross(v[1] - v[0], v[2] - v[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        # view-space normal (right, up, fwd components)
        nv = np.array([n @ right, n @ up, n @ fwd])
        # camera looks along +fwd into the scene; a face is front-facing when its
        # normal points back toward the camera, i.e. nv[2] < 0. Orient + cull.
        if nv[2] > 0:
            n, nv = -n, -nv
        if nv[2] > -1e-6:
            continue                    # edge-on: skip
        px, py, z = _project_px(v, right, up, fwd, s, cx, cy, half)
        poly = np.stack([px, py], axis=1)
        faces.append({"poly": poly, "normal": nv, "depth": float(np.mean(z))})
    return faces
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/python -m pytest tests/test_shade.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/shade.py tests/test_shade.py
git commit -m "feat(shade): faces_from_tris — front-facing polygons + view normals"
```

---

### Task 6: `shade.py` — faces from analytic surfaces (disc, ring, cylinder bands)

**Files:**
- Modify: `brick_icons/shade.py`
- Test: `tests/test_shade.py`

**Approach:** Reuse the analytic rec geometry (`R`, `t`, `sector`, `inner`, `kind`). Sample each surface into polygons in px-space:
- `disc`: one filled polygon = the top circle sampled at ~48 points; normal = axis `R[:,1]`.
- `ring`: annulus → still fill as the outer disc polygon (inner hole is overpainted by whatever sits in it; acceptable for opaque painter compositing). Normal = axis.
- `cyli`: wall split into `bands` angular sectors between the base ring and the top ring; each band is a 4-point quad polygon; normal = outward radial at the band's mid-angle.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shade.py  (add)
def test_faces_from_analytic_cylinder_bands_and_disc():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    cyl = {"kind": "cyli", "sector": 360.0, "inner": 0, "R": R, "t": t}
    disc = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    faces = shade.faces_from_analytic([cyl, disc], right, up, fwd,
                                      s=2.0, cx=0.0, cy=0.0, half=50.0, bands=6)
    kinds = [f["kind"] for f in faces]
    assert kinds.count("disc") == 1
    # 6 wall bands requested; front-facing subset survives (>=1, <=6)
    assert 1 <= kinds.count("cyli") <= 6
    for f in faces:
        assert f["poly"].shape[1] == 2 and abs(np.linalg.norm(f["normal"]) - 1) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py::test_faces_from_analytic_cylinder_bands_and_disc -v`
Expected: FAIL — `AttributeError: module 'brick_icons.shade' has no attribute 'faces_from_analytic'`.

- [ ] **Step 3: Implement `faces_from_analytic`**

```python
# brick_icons/shade.py  (add)
def _radius_pts(rec, thetas, level):
    """World points on the rec's circle at `thetas` (radians), `level` along axis
    (0 = base ring, 1 = top ring). Honors ring inner/outer radius."""
    R = np.asarray(rec["R"], float); C = np.asarray(rec["t"], float)
    r = (rec["inner"] + 1) if rec["kind"] == "ring" else 1.0
    U, A, V = R[:, 0], R[:, 1], R[:, 2]
    base = C + level * A
    return base + r * (np.cos(thetas)[:, None] * U + np.sin(thetas)[:, None] * V)


def faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half, bands=6):
    faces = []
    for rec in analytic:
        kind = rec["kind"]
        if kind == "edge":
            continue
        R = np.asarray(rec["R"], float)
        sect = math.radians(rec["sector"])
        if kind in ("disc", "ring"):
            th = np.linspace(0.0, sect, 48)
            w = _radius_pts(rec, th, 0.0)
            px, py, z = _project_px(w, right, up, fwd, s, cx, cy, half)
            n = R[:, 1]; n = n / np.linalg.norm(n)
            nv = np.array([n @ right, n @ up, n @ fwd])
            if nv[2] > 0:
                nv = -nv
            faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                          "depth": float(np.mean(z)), "kind": kind})
        elif kind == "cyli":
            edges = np.linspace(0.0, sect, bands + 1)
            for i in range(bands):
                a0, a1 = edges[i], edges[i + 1]
                th = np.array([a0, a1])
                base = _radius_pts(rec, th, 0.0)     # (2,3)
                top = _radius_pts(rec, th, 1.0)      # (2,3)
                quad = np.array([base[0], base[1], top[1], top[0]])
                # outward radial normal at mid-angle
                am = 0.5 * (a0 + a1)
                U, V = R[:, 0], R[:, 2]
                n = math.cos(am) * U + math.sin(am) * V
                n = n / np.linalg.norm(n)
                nv = np.array([n @ right, n @ up, n @ fwd])
                if nv[2] > 0:
                    continue                         # band faces away: cull
                px, py, z = _project_px(quad, right, up, fwd, s, cx, cy, half)
                faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                              "depth": float(np.mean(z)), "kind": kind})
    return faces
```

Also add `"kind": "tri"` to the dicts returned by `faces_from_tris` (Task 5) for uniformity — edit that append to include `"kind": "tri"`.

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/python -m pytest tests/test_shade.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/shade.py tests/test_shade.py
git commit -m "feat(shade): faces_from_analytic — disc/ring fills + cylinder bands"
```

---

### Task 7: `ShadingStyle` + `flat3` tone mapping

**Files:**
- Modify: `brick_icons/shade.py`
- Test: `tests/test_shade.py`

**flat3 classification (view space, normal `nv = [nx, ny, nz]`):**
- `up = ny` (view-up component). If `up > 0.5` → **TOP** (lightest).
- else side: if `nx < 0` → **LEFT** (mid); else → **RIGHT** (dark).

Palette = three greys scaled from `part_color` (default `(157,157,157)` — LDraw light grey): TOP ×1.30, LEFT ×0.85, RIGHT ×0.60, each clamped to [0,255], emitted as `#rrggbb`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shade.py  (add)
def test_flat3_tone_by_orientation():
    from brick_icons import shade
    style = shade.Flat3Style(part_color=(160, 160, 160))
    top = style.tone(np.array([0.0, 1.0, -0.1]))
    left = style.tone(np.array([-1.0, 0.0, -0.1]))
    right = style.tone(np.array([1.0, 0.0, -0.1]))
    assert top != left != right and top != right
    # top is lightest -> largest luminance hex
    def lum(h): return int(h[1:3], 16)
    assert lum(top) > lum(left) > lum(right)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py::test_flat3_tone_by_orientation -v`
Expected: FAIL — `AttributeError: module 'brick_icons.shade' has no attribute 'Flat3Style'`.

- [ ] **Step 3: Implement the style**

```python
# brick_icons/shade.py  (add)
def _hex(rgb):
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


class ShadingStyle:
    def tone(self, nv) -> str:
        raise NotImplementedError


class Flat3Style(ShadingStyle):
    """Three tones by dominant face orientation: top / left / right."""
    def __init__(self, part_color=(157, 157, 157)):
        self.top = _hex([c * 1.30 for c in part_color])
        self.left = _hex([c * 0.85 for c in part_color])
        self.right = _hex([c * 0.60 for c in part_color])

    def tone(self, nv):
        if nv[1] > 0.5:
            return self.top
        return self.left if nv[0] < 0 else self.right


STYLES = {"flat3": Flat3Style}


def make_style(name, part_color=(157, 157, 157)):
    return STYLES[name](part_color=part_color)


def parse_hex_color(spec, default=(157, 157, 157)):
    """'0xRRGGBB' or '#RRGGBB' or 'RRGGBB' -> (r, g, b); default on failure."""
    if not spec:
        return default
    s = str(spec).lstrip("#").lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        v = int(s, 16)
        return ((v >> 16) & 255, (v >> 8) & 255, v & 255)
    except ValueError:
        return default
```

Add a matching test to `tests/test_shade.py`:

```python
def test_parse_hex_color():
    from brick_icons import shade
    assert shade.parse_hex_color("0xFF8040") == (255, 128, 64)
    assert shade.parse_hex_color("#00ff00") == (0, 255, 0)
    assert shade.parse_hex_color(None) == (157, 157, 157)
    assert shade.parse_hex_color("nonsense") == (157, 157, 157)
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/python -m pytest tests/test_shade.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/shade.py tests/test_shade.py
git commit -m "feat(shade): Flat3Style tone mapping + style registry"
```

---

### Task 8: Painter-sorted fill emission + SVG fill layer

**Files:**
- Modify: `brick_icons/shade.py` (compose fills), `brick_icons/trace.py` (write fills)
- Test: `tests/test_shade.py`, `tests/test_trace.py`

- [ ] **Step 1: Write the failing test (fill ops)**

```python
# tests/test_shade.py  (add)
def test_fill_ops_painter_sorted_back_to_front():
    from brick_icons import shade
    style = shade.Flat3Style()
    faces = [
        {"poly": np.array([[0, 0], [1, 0], [0, 1]]), "normal": np.array([0, 1, -1.0]),
         "depth": 5.0, "kind": "tri"},   # far
        {"poly": np.array([[0, 0], [2, 0], [0, 2]]), "normal": np.array([0, 1, -1.0]),
         "depth": 1.0, "kind": "tri"},   # near
    ]
    ops = shade.fill_ops(faces, style)
    assert [o["depth"] for o in ops] == [5.0, 1.0]   # far first
    assert "d" in ops[0] and ops[0]["fill"].startswith("#")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py::test_fill_ops_painter_sorted_back_to_front -v`
Expected: FAIL — `AttributeError: module 'brick_icons.shade' has no attribute 'fill_ops'`.

- [ ] **Step 3: Implement `fill_ops` and an affine remapper**

```python
# brick_icons/shade.py  (add)
def _poly_d(poly):
    cmds = [f"M {poly[0,0]:.2f} {poly[0,1]:.2f}"]
    for p in poly[1:]:
        cmds.append(f"L {p[0]:.2f} {p[1]:.2f}")
    cmds.append("Z")
    return " ".join(cmds)


def fill_ops(faces, style):
    """Painter-sorted (far->near) fill ops: {'d': path, 'fill': color, 'depth': z}."""
    ops = []
    for f in sorted(faces, key=lambda f: -f["depth"]):
        ops.append({"d": _poly_d(f["poly"]), "fill": style.tone(f["normal"]),
                    "depth": f["depth"]})
    return ops


def apply_affine_faces(faces, f, ox, oy):
    """Remap face polygons through the same fit affine used for segments."""
    out = []
    for face in faces:
        p = face["poly"]
        q = np.stack([p[:, 0] * f + ox, p[:, 1] * f + oy], axis=1)
        out.append({**face, "poly": q})
    return out
```

- [ ] **Step 4: Write the failing test (SVG writes fills under strokes)**

```python
# tests/test_trace.py  (add)
def test_segments_to_svg_writes_fill_layer(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    fills = [{"d": "M 0 0 L 10 0 L 0 10 Z", "fill": "#cccccc", "depth": 1.0}]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "f.svg", fills=fills)
    txt = out.read_text()
    # fill path appears before the stroke group (painter: fills under strokes)
    assert txt.index('fill="#cccccc"') < txt.index('<g stroke="black"')
    assert 'stroke="none"' in txt
```

- [ ] **Step 5: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_trace.py::test_segments_to_svg_writes_fill_layer -v`
Expected: FAIL — `TypeError: segments_to_svg() got an unexpected keyword argument 'fills'`.

- [ ] **Step 6: Add a `fills` layer to `segments_to_svg`**

Add `fills=None` to the signature. After the `<rect .../>` line and BEFORE the stroke `<g ...>` line, insert:

```python
    if fills:
        parts.append('<g stroke="none">')
        for fo in fills:
            parts.append(f'<path d="{fo["d"]}" fill="{fo["fill"]}"/>')
        parts.append("</g>")
```

(So the parts list becomes: root, rect, [fills group], stroke group, ops, `</g>`, `</svg>`. Build `parts` as root+rect first, then the `if fills` block, then append the stroke `<g>` and loop — reorder the existing initialization so the stroke group is appended after the fills block rather than in the initial list literal.)

- [ ] **Step 7: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_shade.py tests/test_trace.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add brick_icons/shade.py brick_icons/trace.py tests/test_shade.py tests/test_trace.py
git commit -m "feat(shade,trace): painter-sorted fill ops + SVG fill layer"
```

---

### Task 9: Wire shading into the outline pipeline + CLI

**Files:**
- Modify: `brick_icons/hlr.py` (`visible_segments` returns faces too), `brick_icons/config.py`, `brick_icons/cli.py`
- Test: `tests/test_cli.py`

**Design:** `visible_segments` also returns raw faces (px-space, pre-fit) so `process_one` can fit them with the same affine and pass fills to `segments_to_svg`. Faces are produced inside `_visible_segments_*` where `s, cx, cy` (and `half = render_px/2`) are in scope.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py  (add)
def test_shade_style_flat3_adds_fills(tmp_path):
    from brick_icons import cli
    cli.main(["3001", "--format", "svg", "--shading", "outline",
              "--shade-style", "flat3", "--out", str(tmp_path)])
    txt = (tmp_path / "3001.svg").read_text()
    assert 'stroke="none"' in txt and 'fill="#' in txt
    # default (no shade style) has no fill layer
    cli.main(["3001", "--format", "svg", "--shading", "outline", "--out", str(tmp_path / "n")])
    assert 'stroke="none"' not in (tmp_path / "n" / "3001.svg").read_text()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_shade_style_flat3_adds_fills -v`
Expected: FAIL — unrecognized argument `--shade-style` (or no fills present).

- [ ] **Step 3: Produce faces in `_visible_segments_*` and put them in the `faces` field**

`shade` imports `hlr`, so import `shade` lazily inside these functions to avoid a circular import.

In `_visible_segments_analytic`, replace `return VisResult(segs, _ops_bbox(segs), s, [], [], [])` with:

```python
    from . import shade
    faces = shade.faces_from_tris(np.array(out["tri"]), right, up, fwd, s, cx, cy, half) \
        if out["tri"] else []
    faces += shade.faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half)
    return VisResult(segs, _ops_bbox(segs), s, faces, analytic, [])
```

In `_visible_segments_faceted` (`half = render_px / 2`), replace its final return with:

```python
    from . import shade
    faces = shade.faces_from_tris(tri, right, up, fwd, s, cx, cy, render_px / 2) if len(tri) else []
    return VisResult(segs, (min(xs), min(ys), max(xs), max(ys)), s, faces, [], [])
```

(The `analytic` field is populated here for the analytic path so Task 10 can build highlights from it; the faceted path has none.)

- [ ] **Step 4: Update `process_one` to build and pass fills**

At the top of the outline branch, use the `VisResult` fields and prep the style:

```python
        res = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                   render_px=cfg.render_px)
        segs, bbox, s, faces = res.segs, res.bbox, res.s, res.faces
        style = None
        if cfg.shade_style != "none":
            pc = shade.parse_hex_color(cfg.part_color) if cfg.part_color else (157, 157, 157)
            style = shade.make_style(cfg.shade_style, part_color=pc)
```

(`parse_hex_color` is added in Task 7, so it exists here.)

Add `from . import shade` to `cli.py` imports. For `parse_hex_color`: if `render` lacks it, inline `pc = (157,157,157)` for now and leave a follow-up — but check `render.py` first; the existing `--part-color` handling shows the parse to reuse.

In the SVG sub-branch, when building the fit/shifted segments, also fit the faces with the SAME affine and compute fills. For `fit` mode:

```python
            fit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
            fills = None
            if style is not None:
                f, ox, oy = hlr.fit_affine(bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                fills = shade.fill_ops(shade.apply_affine_faces(faces, f, ox, oy), style)
            trace.segments_to_svg(fit, cfg.width, cfg.height, out_dir / f"{name}.svg",
                                  line_px=cfg.line_width, sil_px=cfg.silhouette_width, fills=fills)
```

For `physical` mode, compute `f, ox, oy` from the same shifted bbox used for the segments and pass `fills=` into the physical `segments_to_svg` call (add `fills=fills` to that call; the `fills` block is identical using the shifted bbox passed to `fit_affine`).

- [ ] **Step 5: Add config + CLI for `shade_style`**

In `config.py` DEFAULTS: `"shade_style": "none",`. Add `shade_style: str` to Config and `shade_style=str(data["shade_style"]),` to `load_config`.

In `cli.py::_parse_args`: `p.add_argument("--shade-style", dest="shade_style", choices=["none", "flat3", "cel", "gradient"])`. In overrides: `"shade_style": args.shade_style,`.

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: PASS (whole suite).

- [ ] **Step 7: Render + visually confirm (show inline)**

Run:
```bash
.venv/bin/python -m brick_icons.cli 3001 3941 3040b --format svg --shading outline \
  --shade-style flat3 --out out/shade-check
cd out/shade-check && for f in *.svg; do qlmanage -t -s 512 -o . "$f" >/dev/null 2>&1; done
```
Open the PNGs and confirm flat 3-tone fills sit correctly under the crisp outlines.

- [ ] **Step 8: Commit**

```bash
git add brick_icons/hlr.py brick_icons/config.py brick_icons/cli.py tests/test_cli.py
git commit -m "feat: --shade-style flat3 interior shading in outline SVGs"
```

---

## Phase 3 — Highlights

### Task 10: Diffuse specular overlay + CLI

**Files:**
- Modify: `brick_icons/shade.py` (highlight overlay), `brick_icons/trace.py` (defs/overlay), `brick_icons/config.py`, `brick_icons/cli.py`
- Test: `tests/test_shade.py`, `tests/test_trace.py`

**Design:** For up-facing curved tops (analytic `disc` recs whose axis points up in view), emit a broad, low-opacity **radial gradient** ellipse centered on the disc, radius ≈ the disc's projected extent, peak opacity = `highlight_strength` (default 0.15), falling to 0 at the rim. Emitted as `<defs><radialGradient>` + a filled ellipse, layered above fills. Off unless `--highlights`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_shade.py  (add)
def test_highlight_ops_only_for_upfacing_discs():
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    R = np.eye(3); t = np.zeros(3)
    disc_up = {"kind": "disc", "sector": 360.0, "inner": 0, "R": R, "t": t}
    hi = shade.highlight_ops([disc_up], right, up, fwd, s=2.0, cx=0.0, cy=0.0,
                             half=50.0, strength=0.15)
    assert len(hi) == 1
    assert hi[0]["opacity"] <= 0.15 and hi[0]["cx"] is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py::test_highlight_ops_only_for_upfacing_discs -v`
Expected: FAIL — no `highlight_ops`.

- [ ] **Step 3: Implement `highlight_ops`**

```python
# brick_icons/shade.py  (add)
def highlight_ops(analytic, right, up, fwd, s, cx, cy, half, strength=0.15):
    """Very diffuse speculars on up-facing disc tops: soft radial gradient blobs."""
    ops = []
    for rec in analytic:
        if rec["kind"] != "disc":
            continue
        R = np.asarray(rec["R"], float)
        n = R[:, 1] / np.linalg.norm(R[:, 1])
        nv_up = (n @ up)
        if abs(nv_up) < 0.5:            # not clearly up/down facing
            continue
        th = np.linspace(0, 2 * math.pi, 24)
        w = _radius_pts(rec, th, 0.0)
        px, py, _ = _project_px(w, right, up, fwd, s, cx, cy, half)
        cxp, cyp = float(px.mean()), float(py.mean())
        rr = float(max(px.max() - px.min(), py.max() - py.min()) / 2.0)
        ops.append({"cx": cxp, "cy": cyp, "r": rr, "opacity": strength})
    return ops
```

- [ ] **Step 4: Write the failing SVG test**

```python
# tests/test_trace.py  (add)
def test_segments_to_svg_writes_highlight_gradient(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    hi = [{"cx": 5.0, "cy": 5.0, "r": 4.0, "opacity": 0.15}]
    out = _trace.segments_to_svg(segs, 20, 20, tmp_path / "h.svg", highlights=hi)
    txt = out.read_text()
    assert "radialGradient" in txt and "<ellipse" in txt
```

- [ ] **Step 5: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_trace.py::test_segments_to_svg_writes_highlight_gradient -v`
Expected: FAIL — no `highlights` kwarg.

- [ ] **Step 6: Add `highlights` layer to `segments_to_svg`**

Add `highlights=None` to the signature. After the fills block (and before the stroke group), insert:

```python
    if highlights:
        defs = ['<defs>']
        blobs = []
        for i, h in enumerate(highlights):
            gid = f"hl{i}"
            defs.append(
                f'<radialGradient id="{gid}">'
                f'<stop offset="0%" stop-color="white" stop-opacity="{h["opacity"]:.3f}"/>'
                f'<stop offset="100%" stop-color="white" stop-opacity="0"/>'
                f'</radialGradient>')
            blobs.append(
                f'<ellipse cx="{h["cx"]:.2f}" cy="{h["cy"]:.2f}" '
                f'rx="{h["r"]:.2f}" ry="{h["r"]:.2f}" fill="url(#{gid})" stroke="none"/>')
        defs.append('</defs>')
        parts += defs + ['<g stroke="none">'] + blobs + ['</g>']
```

- [ ] **Step 7: Config + CLI + wire into `process_one`**

`config.py` DEFAULTS: `"highlights": False,` and `"highlight_strength": 0.15,`. Add to Config: `highlights: bool`, `highlight_strength: float`. In `load_config`: `highlights=bool(data["highlights"]), highlight_strength=float(data["highlight_strength"]),`.

`cli.py`: `p.add_argument("--highlights", dest="highlights", action="store_true", default=None)` and `p.add_argument("--highlight-strength", dest="highlight_strength", type=float)`. Overrides: `"highlights": args.highlights, "highlight_strength": args.highlight_strength,`.

`highlight_ops` needs `right/up/fwd/s/cx/cy/half`, which are only in scope inside `_visible_segments_*`. So compute pre-fit highlight ops there and return them in the `highlights` field of `VisResult`; `process_one` then remaps them through the fit affine and applies `highlight_strength`.

In `_visible_segments_analytic`, change its return to populate the `highlights` field (baking `strength=1.0` now; scaled later):

```python
    hi = shade.highlight_ops(analytic, right, up, fwd, s, cx, cy, half, strength=1.0)
    return VisResult(segs, _ops_bbox(segs), s, faces, analytic, hi)
```

Add `remap_highlights` to `shade.py`:

```python
def remap_highlights(his, f, ox, oy, strength):
    return [{"cx": h["cx"] * f + ox, "cy": h["cy"] * f + oy, "r": h["r"] * f,
             "opacity": strength} for h in his]
```

with a matching unit test in `tests/test_shade.py`:

```python
def test_remap_highlights_applies_affine_and_strength():
    from brick_icons import shade
    out = shade.remap_highlights([{"cx": 10.0, "cy": 20.0, "r": 5.0, "opacity": 1.0}],
                                 f=2.0, ox=1.0, oy=3.0, strength=0.15)
    assert out[0] == {"cx": 21.0, "cy": 43.0, "r": 10.0, "opacity": 0.15}
```

In `process_one`, build `hi` alongside `fills` in both the `fit` and `physical` sub-branches (using the same `f, ox, oy`):

```python
            hi = None
            if cfg.highlights and res.highlights:
                hi = shade.remap_highlights(res.highlights, f, ox, oy, cfg.highlight_strength)
```

and pass `highlights=hi` to the corresponding `segments_to_svg` call.

- [ ] **Step 8: Run tests + render check**

Run: `.venv/bin/python -m pytest tests/ -v` → PASS.
Then:
```bash
.venv/bin/python -m brick_icons.cli 3001 --format svg --shading outline \
  --shade-style flat3 --highlights --out out/hl-check
qlmanage -t -s 512 -o out/hl-check out/hl-check/3001.svg >/dev/null 2>&1
```
Confirm a soft, broad sheen on the stud tops (no hard dot). Show inline.

- [ ] **Step 9: Commit**

```bash
git add brick_icons/shade.py brick_icons/trace.py brick_icons/hlr.py brick_icons/config.py brick_icons/cli.py tests/
git commit -m "feat: optional diffuse specular highlights on stud tops"
```

---

## Phase 4 — Library generator

### Task 11: Part header parsing + filter predicate

**Files:**
- Create: `brick_icons/library.py`
- Test: `tests/test_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library.py  (new file)
from brick_icons import library


def test_parse_header_and_accept():
    hdr = "0 Brick  2 x  4\n0 !LDRAW_ORG Part UPDATE 2004-03\n"
    info = library.parse_header(hdr.splitlines())
    assert info.title == "Brick  2 x  4"
    assert info.category == "Brick"
    assert info.org == "Part"
    assert library.is_sortable(info) is True


def test_reject_sticker_shortcut_moved_pattern():
    def info(t, org="Part"):
        return library.parse_header([f"0 {t}", f"0 !LDRAW_ORG {org} UPDATE x"])
    assert library.is_sortable(info("Sticker 1 x 1")) is False
    assert library.is_sortable(info("Brick 2 x 4", org="Shortcut")) is False
    assert library.is_sortable(info("Moved to 3001")) is False
    assert library.is_sortable(info("Tile 2 x 2 with Pattern")) is False
    assert library.is_sortable(info("~Brick 2 x 4")) is False
    assert library.is_sortable(info("Minifig Head")) is False
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_library.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.library'`.

- [ ] **Step 3: Implement header parse + filter**

```python
# brick_icons/library.py  (new file)
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ALLOWED_CATEGORIES = {
    "Brick", "Plate", "Tile", "Slope", "Technic", "Wedge", "Panel",
    "Cylinder", "Cone", "Dish", "Bar", "Bracket", "Hinge", "Wing", "Baseplate",
}
EXCLUDE_TITLE_SUBSTR = ("Sticker", "Pattern", "Moved")
_ORG = re.compile(r"!LDRAW_ORG\s+(\w+)")


@dataclass(frozen=True)
class PartInfo:
    title: str
    category: str
    org: str


def parse_header(lines) -> PartInfo:
    title = ""
    org = ""
    for ln in lines:
        s = ln.rstrip("\n")
        if not title and s.startswith("0 ") and "!LDRAW_ORG" not in s and "Name:" not in s:
            title = s[2:].strip()
        m = _ORG.search(s)
        if m and not org:
            org = m.group(1)
        if title and org:
            break
    stripped = title.lstrip("~_ ")
    category = stripped.split()[0] if stripped else ""
    return PartInfo(title=title, category=category, org=org)


def is_sortable(info: PartInfo) -> bool:
    if info.org != "Part":
        return False
    if info.title[:1] in ("~", "_"):
        return False
    if any(sub in info.title for sub in EXCLUDE_TITLE_SUBSTR):
        return False
    return info.category in ALLOWED_CATEGORIES
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/python -m pytest tests/test_library.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/library.py tests/test_library.py
git commit -m "feat(library): part header parse + sortable-part filter"
```

---

### Task 12: Enumerate + select parts from the LDraw tree

**Files:**
- Modify: `brick_icons/library.py`
- Test: `tests/test_library.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_library.py  (add)
def test_select_parts_finds_known_ids():
    from brick_icons import library
    ids = set(library.select_parts("vendor/ldraw", limit=None))
    # curated staples must be present and noise absent
    assert "3001" in ids and "3020" in ids and "3040b" in ids
    assert all(not i.endswith(".dat") for i in ids)
    assert len(ids) > 200
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_library.py::test_select_parts_finds_known_ids -v`
Expected: FAIL — no `select_parts`.

- [ ] **Step 3: Implement `select_parts`**

```python
# brick_icons/library.py  (add)
def _read_header_lines(path: Path, n=12):
    out = []
    with open(path, "r", errors="replace") as fh:
        for _ in range(n):
            ln = fh.readline()
            if not ln:
                break
            out.append(ln)
    return out


def select_parts(ldraw_dir, limit=None, category=None):
    """Sorted list of part ids (no .dat) that pass the sortable filter."""
    parts_dir = Path(ldraw_dir) / "parts"
    ids = []
    for dat in sorted(parts_dir.glob("*.dat")):
        info = parse_header(_read_header_lines(dat))
        if not is_sortable(info):
            continue
        if category and info.category != category:
            continue
        ids.append(dat.stem)
        if limit and len(ids) >= limit:
            break
    return ids
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/bin/python -m pytest tests/test_library.py::test_select_parts_finds_known_ids -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/library.py tests/test_library.py
git commit -m "feat(library): select_parts enumerates sortable catalog parts"
```

---

### Task 13: Batch render + manifest + resumable + parallel CLI

**Files:**
- Modify: `brick_icons/library.py` (batch driver + `__main__`)
- Test: `tests/test_library.py`

**Design:** `render_library(cfg_overrides, out_dir, ldraw_dir, ...)` selects parts, renders each to `out_dir/<category>/<id>.svg` via a worker that calls `cli.process_one` with a physical-scale outline config, and writes `manifest.json`. Resumable (skip existing SVG unless `force`); parallel via `ProcessPoolExecutor`. Errors captured per-part.

- [ ] **Step 1: Write the failing test (single-process, tiny limit)**

```python
# tests/test_library.py  (add)
import json


def test_render_library_small(tmp_path):
    from brick_icons import library
    manifest = library.render_library(
        out_dir=str(tmp_path), ldraw_dir="vendor/ldraw",
        limit=3, workers=1, shade_style="flat3")
    assert (tmp_path / "manifest.json").exists()
    data = json.loads((tmp_path / "manifest.json").read_text())
    assert len(data) == 3
    ok = [r for r in data if r["status"] == "ok"]
    assert ok, "expected at least one successful render"
    r = ok[0]
    assert r["width_mm"] > 0 and r["height_mm"] > 0 and r["category"]
    svg = tmp_path / r["category"] / f'{r["id"]}.svg'
    assert svg.exists() and svg.read_text().startswith("<svg")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_library.py::test_render_library_small -v`
Expected: FAIL — no `render_library`.

- [ ] **Step 3: Implement the batch driver**

```python
# brick_icons/library.py  (add)
import json
from concurrent.futures import ProcessPoolExecutor

from .config import load_config
from . import cli as _cli


def _render_one(args):
    part, out_dir, ldraw_dir, shade_style, highlights = args
    from pathlib import Path
    import re as _re
    info = parse_header(_read_header_lines(Path(ldraw_dir) / "parts" / f"{part}.dat"))
    cat_dir = Path(out_dir) / info.category
    svg = cat_dir / f"{part}.svg"
    rec = {"id": part, "title": info.title, "category": info.category,
           "width_mm": 0.0, "height_mm": 0.0, "status": "ok"}
    try:
        cfg = load_config(toml_path=None, root=".", overrides={
            "fmt": "svg", "shading": "outline", "scale_mode": "physical",
            "shade_style": shade_style, "highlights": highlights,
            "ldraw_dir": ldraw_dir})
        _cli.process_one(cfg, part, cat_dir)
        if not svg.exists():
            rec["status"] = "skipped-empty"
        else:
            txt = svg.read_text()
            m = _re.search(r'width="([\d.]+)mm" height="([\d.]+)mm"', txt)
            if m:
                rec["width_mm"], rec["height_mm"] = float(m.group(1)), float(m.group(2))
    except Exception as e:                       # noqa: BLE001 — batch must not abort
        rec["status"] = f"error:{type(e).__name__}:{e}"
    return rec


def render_library(out_dir, ldraw_dir="vendor/ldraw", limit=None, category=None,
                   workers=4, shade_style="flat3", highlights=False, force=False):
    from pathlib import Path
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ids = select_parts(ldraw_dir, limit=limit, category=category)
    tasks = [(p, out_dir, ldraw_dir, shade_style, highlights) for p in ids]
    records = []
    if workers <= 1:
        records = [_render_one(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            records = list(ex.map(_render_one, tasks))
    (Path(out_dir) / "manifest.json").write_text(json.dumps(records, indent=2))
    return records
```

(Resumable: add a `force` check inside `_render_one` — `if svg.exists() and not force: read mm and return ok` — thread `force` into the task tuple. Keep the first pass simple; add the skip-existing shortcut here.)

- [ ] **Step 4: Add `__main__` CLI**

```python
# brick_icons/library.py  (add at bottom)
def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(prog="brick-icons-library")
    p.add_argument("--out", default="out/library")
    p.add_argument("--ldraw-dir", default="vendor/ldraw")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--category", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--shade-style", default="flat3",
                   choices=["none", "flat3", "cel", "gradient"])
    p.add_argument("--highlights", action="store_true")
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    recs = render_library(a.out, a.ldraw_dir, a.limit, a.category, a.workers,
                          a.shade_style, a.highlights, a.force)
    ok = sum(1 for r in recs if r["status"] == "ok")
    print(f"library: {ok}/{len(recs)} ok -> {a.out}/manifest.json")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv/bin/python -m pytest tests/test_library.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/library.py tests/test_library.py
git commit -m "feat(library): resumable parallel batch render + manifest + CLI"
```

---

## Phase 5 — Visual sign-off + full batch

### Task 14: Sample sheet for sign-off

**Files:** none (produces artifacts under `out/`, which is gitignored)

- [ ] **Step 1: Render a representative sample at physical scale, flat3**

```bash
.venv/bin/python -m brick_icons.cli 3001 3941 3068b 3040b 3701 3020 \
  --format svg --shading outline --shade-style flat3 --scale-mode physical \
  --out out/sample
```

- [ ] **Step 2: Build a labeled contact sheet and show it inline**

`qlmanage` rasterizes SVG via WebKit (reliable on macOS). Then tile with PIL:

```bash
cd out/sample && for f in *.svg; do qlmanage -t -s 512 -o . "$f" >/dev/null 2>&1; done
.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw, ImageFont
import glob, math, os
os.chdir("out/sample")
files = sorted(glob.glob("*.svg.png"))
cell, pad, cols, labh = 280, 8, 3, 22
rows = math.ceil(len(files) / cols)
sheet = Image.new("RGB", (cols * cell, rows * (cell + labh)), "white")
d = ImageDraw.Draw(sheet)
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white"); bg.alpha_composite(im); im = bg.convert("RGB")
    im.thumbnail((cell - 2 * pad, cell - 2 * pad))
    r, c = divmod(i, cols); x, y = c * cell, r * (cell + labh)
    sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
    d.rectangle([x, y, x + cell, y + cell + labh], outline="#ccc")
    d.text((x + 4, y + cell + 2), f.replace(".svg.png", ""), fill="black", font=font)
sheet.save("contact.png"); print("wrote out/sample/contact.png")
PY
```

Then use the Read tool on `out/sample/contact.png` to display it inline to the user.

- [ ] **Step 3: STOP for user approval**

Present the contact sheet inline. Get explicit approval of the flat3 look, physical relative sizes, and (if requested) a `--highlights` variant, before running the full batch. Adjust palette factors / `cyl_bands` / light per feedback.

---

### Task 15: Full library batch

**Files:** none (artifacts under `out/library/`)

- [ ] **Step 1: Run the full batch (parallel)**

```bash
.venv/bin/python -m brick_icons.library --out out/library --workers 8 --shade-style flat3
```

- [ ] **Step 2: Sanity-check the manifest**

```bash
.venv/bin/python - <<'PY'
import json, collections
d = json.load(open("out/library/manifest.json"))
c = collections.Counter(r["status"].split(":")[0] for r in d)
print("total", len(d), dict(c))
print("categories", collections.Counter(r["category"] for r in d if r["status"]=="ok"))
PY
```

- [ ] **Step 3: Spot-check a few category dirs visually (show inline)**

Render contact sheets for a couple of categories (e.g. `out/library/Slope`, `out/library/Technic`) and Read them inline. Log the counts of `error:`/`skipped-empty` parts so any systematic renderer gaps are visible rather than silently dropped.

- [ ] **Step 4: Update README**

Document the new flags (`--scale-mode`, `--shade-style`, `--highlights`, `--highlight-strength`, `--light` if added, `--line-mm`/`--silhouette-mm`) and the `python -m brick_icons.library` command in `README.md`. Commit.

```bash
git add README.md
git commit -m "docs: document physical scale, shading styles, and library generator"
```

---

## Notes / deferred

- **`cel` and `gradient` styles**: the `ShadingStyle` interface and `STYLES` registry are in place (Task 7); implementing them is follow-up work — add `CelStyle`/`GradientStyle` classes and register them. Not in this plan's scope beyond the interface.
- **`--light LAT,LONG`**: `flat3` classifies by fixed view-space orientation, so light direction is a no-op for it; wire `--light` when `cel`/`gradient` land (they use `normal·light`). Omitted here to avoid a dead flag.
- **PNG physical scale**: out of scope (SVG only), per spec.
- **`--cyl-bands` flag**: `faces_from_analytic` takes `bands` (default 6), but no CLI/config flag is wired in this plan — 6 is a sensible fixed default. Add `--cyl-bands` + a config field later if band count needs tuning (trivial, mirrors the other flags).
- If `render.parse_hex_color` does not exist (Task 9 Step 4), reuse whatever `--part-color` parsing `process_one`/`render.py` already does, or add a 3-line hex parser to `shade.py` with its own unit test.
