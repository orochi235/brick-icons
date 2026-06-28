# HLR Conditional-Line Outline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `--shading outline` with a pure-Python LDraw hidden-line-removal renderer that emits clean vector SVG + mono/gray PNG, retiring the LDView raster-trace outline.

**Architecture:** New `hlr.py` parses/flattens LDraw `.dat` geometry, projects via a camera, and z-buffers faces to keep only visible type-2 edges and silhouette-passing type-5 conditional lines — returning 2D segments. `trace.py` writes those segments as SVG; `process.py` rasterizes them to mono/gray. `cli.py` routes outline shading to this path (no LDView call). cel/normal/color are untouched.

**Tech Stack:** Python 3, numpy, Pillow. Reference implementation: `scratchpad/hlr_spike.py` (working spike). Design: `docs/superpowers/specs/2026-06-28-hlr-outline-design.md`.

---

## File Structure

- Create `brick_icons/hlr.py` — LDraw parse+flatten, camera, z-buffer HLR → visible 2D segments + helpers. One responsibility: geometry → visible lines.
- Modify `brick_icons/trace.py` — add `segments_to_svg`; later remove `outline_svg`.
- Modify `brick_icons/process.py` — add `draw_segments`/`segments_mono`; later remove `make_outline`, `outline_masks`, `outline_mono`, `_compose_lines`, `_resize_ink`.
- Modify `brick_icons/cli.py` — route `--shading outline` through HLR; drop the old outline branch.
- Modify tests: `tests/test_hlr.py` (new), `tests/test_process.py`, `tests/test_trace.py`, `tests/test_cli.py`.

Segment representation everywhere: tuple `(x1, y1, x2, y2, kind)` with `kind in {"edge", "sil"}`, coords float.

---

### Task 1: LDraw parse + flatten

**Files:**
- Create: `brick_icons/hlr.py`
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hlr.py
import numpy as np
import pytest
from pathlib import Path
from brick_icons import hlr


def test_flatten_collects_typed_geometry(tmp_path):
    # a self-contained .dat: one edge, one triangle, one conditional line
    d = tmp_path / "t.dat"
    d.write_text(
        "2 24 0 0 0 1 0 0\n"
        "3 16 0 0 0 1 0 0 0 1 0\n"
        "5 24 0 0 0 1 0 0 0 1 0 0 -1 0\n"
    )
    out = {"2": [], "5": [], "tri": []}
    hlr.flatten(d, np.eye(3), np.zeros(3), out, roots=[tmp_path])
    assert len(out["2"]) == 1 and out["2"][0].shape == (2, 3)
    assert len(out["tri"]) == 1 and out["tri"][0].shape == (3, 3)
    assert len(out["5"]) == 1 and out["5"][0].shape == (4, 3)


def test_flatten_composes_subfile_transform(tmp_path):
    (tmp_path / "child.dat").write_text("2 24 0 0 0 1 0 0\n")
    parent = tmp_path / "parent.dat"
    # translate child by (10,0,0), identity rotation
    parent.write_text("1 16 10 0 0 1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, roots=[tmp_path])
    seg = out["2"][0]
    assert np.allclose(seg[0], [10, 0, 0]) and np.allclose(seg[1], [11, 0, 0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hlr.py -v`
Expected: FAIL (`ModuleNotFoundError: brick_icons.hlr`).

- [ ] **Step 3: Write minimal implementation**

```python
# brick_icons/hlr.py
from __future__ import annotations
import math
from pathlib import Path
import numpy as np

_text_cache: dict[Path, list[str]] = {}


def default_roots(ldraw_dir: Path) -> list[Path]:
    ldraw_dir = Path(ldraw_dir)
    return [ldraw_dir / "p" / "48", ldraw_dir / "p",
            ldraw_dir / "parts", ldraw_dir / "parts" / "s", ldraw_dir / "models"]


def resolve(name: str, roots: list[Path]) -> Path | None:
    name = name.replace("\\", "/").strip()
    base = name.split("/")[-1]
    for root in roots:
        for cand in (root / name, root / base):
            if cand.exists():
                return cand
    return None


def _lines(path: Path) -> list[str]:
    if path not in _text_cache:
        _text_cache[path] = Path(path).read_text(errors="replace").splitlines()
    return _text_cache[path]


def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0) -> None:
    if depth > 30:
        return
    for ln in _lines(path):
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
            M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
            T = np.array([x, y, z], float)
            sub = resolve(" ".join(tok[14:]), roots)
            if sub is not None:
                flatten(sub, R @ M, R @ T + t, out, roots, depth + 1)
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                if n == 3:
                    out["tri"].append(pts)
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri"].append(pts[[0, 2, 3]])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_hlr.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "feat(hlr): LDraw recursive parse + flatten with transform composition"
```

---

### Task 2: Camera + projection

**Files:**
- Modify: `brick_icons/hlr.py`
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write the failing test**

```python
def test_front_view_axes():
    # front (lat=0,long=0): +X -> +screen_x ; LDraw +Y(down) -> +screen_y (down)
    right, up, fwd = hlr.view_basis(0.0, 0.0)
    P = np.array([[1, 0, 0], [0, 1, 0]], float)
    sx, sy, z = hlr.project(P, right, up, fwd)
    assert sx[0] > 0.5 and abs(sy[0]) < 1e-6      # +X is rightward
    assert sy[1] > 0.5                            # +Y(down) projects downward


def test_view_basis_orthonormal():
    r, u, f = hlr.view_basis(30.0, 45.0)
    for v in (r, u, f):
        assert abs(np.linalg.norm(v) - 1) < 1e-9
    assert abs(r @ u) < 1e-9 and abs(r @ f) < 1e-9 and abs(u @ f) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hlr.py -k view -v`
Expected: FAIL (`AttributeError: view_basis`).

- [ ] **Step 3: Write minimal implementation**

Append to `brick_icons/hlr.py`:

```python
SIGN_Z = -1.0          # tuned so parts face the camera (matches LDView iso)


def view_basis(lat: float, long: float):
    la, lo = math.radians(lat), math.radians(long)
    up_world = np.array([0.0, -1.0, 0.0])          # LDraw Y is down
    d = np.array([math.cos(la) * math.sin(lo), -math.sin(la),
                  SIGN_Z * math.cos(la) * math.cos(lo)])
    forward = -d / np.linalg.norm(d)
    right = np.cross(forward, up_world); right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def project(P: np.ndarray, right, up, forward):
    return P @ right, -(P @ up), P @ forward       # sx, sy(image-down), depth
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_hlr.py -k view -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "feat(hlr): look-at camera + orthographic projection"
```

---

### Task 3: Z-buffer + conditional rule + visibility

**Files:**
- Modify: `brick_icons/hlr.py`
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write the failing test**

```python
def test_conditional_same_side_predicate():
    # control points on the same side -> drawn; opposite -> not
    p1 = np.array([0.0, 0.0]); p2 = np.array([1.0, 0.0])
    assert hlr.same_side(p1, p2, np.array([0.5, 1.0]), np.array([0.5, 2.0])) is True
    assert hlr.same_side(p1, p2, np.array([0.5, 1.0]), np.array([0.5, -2.0])) is False


def test_zbuffer_hides_segment_behind_face():
    # a near triangle covering the center; a segment far behind it is culled
    tri_s = np.array([[[10, 10], [90, 10], [50, 90]]], float)
    tri_z = np.array([[0.0, 0.0, 0.0]], float)        # near (small z)
    zbuf = hlr.rasterize_zbuffer(tri_s, tri_z, 100, 100)
    behind = hlr.clip_visible((30, 40, 70, 40, "edge"), zbuf, 100, 100, depth=5.0, bias=0.01)
    assert behind == []                                # fully hidden
    front = hlr.clip_visible((30, 40, 70, 40, "edge"), zbuf, 100, 100, depth=-5.0, bias=0.01)
    assert len(front) == 1                             # in front -> visible
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hlr.py -k "same_side or zbuffer" -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Append to `brick_icons/hlr.py`:

```python
def same_side(p1, p2, c1, c2) -> bool:
    e = p2 - p1
    cr1 = e[0] * (c1[1] - p1[1]) - e[1] * (c1[0] - p1[0])
    cr2 = e[0] * (c2[1] - p1[1]) - e[1] * (c2[0] - p1[0])
    return cr1 * cr2 > 0


def rasterize_zbuffer(tri_s: np.ndarray, tri_z: np.ndarray, W: int, H: int) -> np.ndarray:
    zbuf = np.full((H, W), np.inf)
    for v, zz in zip(tri_s, tri_z):
        minx = max(int(np.floor(v[:, 0].min())), 0); maxx = min(int(np.ceil(v[:, 0].max())), W - 1)
        miny = max(int(np.floor(v[:, 1].min())), 0); maxy = min(int(np.ceil(v[:, 1].max())), H - 1)
        if maxx < minx or maxy < miny:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1), np.arange(miny, maxy + 1))
        x0, y0 = v[0]; x1, y1 = v[1]; x2, y2 = v[2]
        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-9:
            continue
        a = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / denom
        b = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / denom
        cc = 1 - a - b
        inside = (a >= -1e-4) & (b >= -1e-4) & (cc >= -1e-4)
        z = a * zz[0] + b * zz[1] + cc * zz[2]
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        m = inside & (z < sub)
        sub[m] = z[m]
    return zbuf


def clip_visible(seg, zbuf, W, H, depth, bias):
    """Return list of visible sub-segments. `depth` may be a scalar (uniform) or
    (z1, z2) for per-endpoint depth. Samples the z-buffer along the segment."""
    x1, y1, x2, y2, kind = seg
    z1, z2 = (depth, depth) if np.isscalar(depth) else depth
    n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 2))
    ts = np.linspace(0, 1, n)
    xs = x1 + (x2 - x1) * ts; ys = y1 + (y2 - y1) * ts; zs = z1 + (z2 - z1) * ts
    xi = np.clip(xs.astype(int), 0, W - 1); yi = np.clip(ys.astype(int), 0, H - 1)
    vis = zs <= zbuf[yi, xi] + bias
    runs, i = [], 0
    while i < n:
        if vis[i]:
            j = i
            while j + 1 < n and vis[j + 1]:
                j += 1
            runs.append((xs[i], ys[i], xs[j], ys[j], kind))
            i = j + 1
        else:
            i += 1
    return runs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_hlr.py -k "same_side or zbuffer" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "feat(hlr): z-buffer rasterizer, conditional rule, visibility clip"
```

---

### Task 4: Top-level `visible_segments` + `fit_segments`

**Files:**
- Modify: `brick_icons/hlr.py`
- Test: `tests/test_hlr.py`

Note: type-5 silhouette lines lie ON the curved surface, so they use a larger
bias (`SIL_BIAS`) to avoid self-occlusion while still being hidden by nearer parts.

- [ ] **Step 1: Write the failing test**

```python
import shutil
LIB = Path("vendor/ldraw")
HAVE_LIB = LIB.exists()


def test_fit_segments_centers_in_box():
    segs = [(0.0, 0.0, 10.0, 0.0, "edge"), (0.0, 0.0, 0.0, 10.0, "edge")]
    fit = hlr.fit_segments(segs, (0, 0, 10, 10), 100, 100, margin=10, scale=1.0)
    xs = [c for s in fit for c in (s[0], s[2])]
    ys = [c for s in fit for c in (s[1], s[3])]
    assert min(xs) >= 9 and max(xs) <= 91 and min(ys) >= 9 and max(ys) <= 91


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_visible_segments_on_real_part():
    segs, bbox = hlr.visible_segments("3701", LIB, lat=30, long=45, render_px=600)
    assert len(segs) > 50
    assert all(s[4] in ("edge", "sil") for s in segs)
    assert bbox[2] > bbox[0] and bbox[3] > bbox[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_hlr.py -k "fit_segments or visible_segments" -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Append to `brick_icons/hlr.py`:

```python
EDGE_BIAS = 0.004      # fraction of depth range
SIL_BIAS = 0.03        # larger: silhouette lines sit on their own surface


def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900):
    roots = default_roots(ldraw_dir)
    path = resolve(part + ".dat", roots) if not str(part).endswith(".dat") else Path(part)
    out = {"2": [], "5": [], "tri": []}
    flatten(path, np.eye(3), np.zeros(3), out, roots)
    right, up, fwd = view_basis(lat, long)

    tri = np.array(out["tri"]) if out["tri"] else np.zeros((0, 3, 3))
    fitpts = tri.reshape(-1, 3) if len(tri) else np.array(out["2"]).reshape(-1, 3)
    sx, sy, _ = project(fitpts, right, up, fwd)
    minx, maxx, miny, maxy = sx.min(), sx.max(), sy.min(), sy.max()
    span = max(maxx - minx, maxy - miny) or 1.0
    s = (render_px - 20) / span
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    def to_px(P):
        a, b, z = project(P, right, up, fwd)
        return (a - cx) * s + render_px / 2, (b - cy) * s + render_px / 2, z

    if len(tri):
        tpx, tpy, tz = to_px(tri.reshape(-1, 3))
        tri_s = np.stack([tpx, tpy], 1).reshape(-1, 3, 2)
        tri_z = tz.reshape(-1, 3)
        zbuf = rasterize_zbuffer(tri_s, tri_z, render_px, render_px)
        zrange = tri_z.max() - tri_z.min() or 1.0
    else:
        zbuf = np.full((render_px, render_px), np.inf); zrange = 1.0

    segs = []
    for e in out["2"]:
        ax, ay, az = to_px(e[0:1]); bx, by, bz = to_px(e[1:2])
        segs += clip_visible((ax[0], ay[0], bx[0], by[0], "edge"), zbuf, render_px,
                             render_px, (az[0], bz[0]), EDGE_BIAS * zrange)
    for q in out["5"]:
        px, py, pz = to_px(q)
        p1 = np.array([px[0], py[0]]); p2 = np.array([px[1], py[1]])
        if math.hypot(*(p2 - p1)) < 0.5:
            continue
        if same_side(p1, p2, np.array([px[2], py[2]]), np.array([px[3], py[3]])):
            segs += clip_visible((px[0], py[0], px[1], py[1], "sil"), zbuf, render_px,
                                 render_px, (pz[0], pz[1]), SIL_BIAS * zrange)

    xs = [c for sg in segs for c in (sg[0], sg[2])] or [0, 1]
    ys = [c for sg in segs for c in (sg[1], sg[3])] or [0, 1]
    return segs, (min(xs), min(ys), max(xs), max(ys))


def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    scale = max(0.01, min(1.0, scale))
    bx0, by0, bx1, by1 = bbox
    bw, bh = (bx1 - bx0) or 1.0, (by1 - by0) or 1.0
    iw = max(1.0, (W - 2 * margin) * scale); ih = max(1.0, (H - 2 * margin) * scale)
    f = min(iw / bw, ih / bh)
    ox = (W - bw * f) / 2 - bx0 * f
    oy = (H - bh * f) / 2 - by0 * f
    return [(x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k)
            for (x1, y1, x2, y2, k) in segs]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_hlr.py -k "fit_segments or visible_segments" -v`
Expected: PASS (real-part test skips if library absent).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "feat(hlr): visible_segments pipeline + fit_segments, silhouette bias fix"
```

---

### Task 5: Rasterize segments (mono/gray) in process.py

**Files:**
- Modify: `brick_icons/process.py`
- Test: `tests/test_process.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_process.py
def test_draw_segments_black_on_white_sized():
    segs = [(10.0, 10.0, 90.0, 10.0, "edge"), (10.0, 10.0, 10.0, 90.0, "sil")]
    img = process.draw_segments(segs, 100, 100, line_px=2, sil_px=4)
    assert img.size == (100, 100) and img.mode == "L"
    a = np.asarray(img)
    assert (a == 0).any() and a.mean() > 200


def test_draw_segments_width_thickens():
    segs = [(10.0, 50.0, 90.0, 50.0, "edge")]
    thin = (np.asarray(process.draw_segments(segs, 100, 100, 1, 1)) < 128).sum()
    thick = (np.asarray(process.draw_segments(segs, 100, 100, 6, 1)) < 128).sum()
    assert thick > thin


def test_segments_mono_is_1bit():
    segs = [(10.0, 50.0, 90.0, 50.0, "edge")]
    m = process.segments_mono(segs, 100, 100, line_px=2, sil_px=3)
    assert m.mode == "1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_process.py -k draw_segments -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Add to `brick_icons/process.py` (uses existing `Image`, `np`; add `ImageDraw` import at top):

```python
def draw_segments(segs, w, h, line_px=2, sil_px=3, supersample=3):
    """Anti-aliased black line-art on white. 'sil' segments use sil_px width."""
    ss = max(1, supersample)
    img = Image.new("L", (w * ss, h * ss), 255)
    dr = ImageDraw.Draw(img)
    for x1, y1, x2, y2, kind in segs:
        wpx = max(1, round((sil_px if kind == "sil" else line_px) * ss))
        dr.line([(x1 * ss, y1 * ss), (x2 * ss, y2 * ss)], fill=0, width=wpx)
    return img.resize((w, h), Image.LANCZOS)


def segments_mono(segs, w, h, line_px=2, sil_px=3, threshold=160):
    g = draw_segments(segs, w, h, line_px, sil_px)
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")
```

Add `ImageDraw` to the existing Pillow import line:
`from PIL import Image, ImageFilter, ImageOps, ImageDraw`

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_process.py -k draw_segments -v` and `-k segments_mono`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/process.py tests/test_process.py
git commit -m "feat(process): rasterize HLR segments to mono/gray line-art"
```

---

### Task 6: SVG output in trace.py

**Files:**
- Modify: `brick_icons/trace.py`
- Test: `tests/test_trace.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_trace.py
from brick_icons import trace as _trace


def test_segments_to_svg_writes_lines(tmp_path):
    segs = [(10.0, 10.0, 90.0, 10.0, "edge"), (10.0, 10.0, 10.0, 90.0, "sil")]
    out = tmp_path / "s.svg"
    _trace.segments_to_svg(segs, 100, 100, out, line_px=2, sil_px=4)
    txt = out.read_text()
    assert 'viewBox="0 0 100 100"' in txt
    assert txt.count("<line") == 2
    assert 'stroke-width="4"' in txt and 'stroke-width="2"' in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_trace.py -k segments_to_svg -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Add to `brick_icons/trace.py`:

```python
def segments_to_svg(segs, w, h, out_path, line_px=2, sil_px=3) -> Path:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
             f'preserveAspectRatio="xMidYMid meet">',
             '<rect width="100%" height="100%" fill="white"/>',
             '<g stroke="black" fill="none" stroke-linecap="round">']
    for x1, y1, x2, y2, kind in segs:
        sw = sil_px if kind == "sil" else line_px
        parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                     f'stroke-width="{sw}"/>')
    parts += ["</g>", "</svg>"]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))
    return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_trace.py -k segments_to_svg -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/trace.py tests/test_trace.py
git commit -m "feat(trace): segments_to_svg vector line-art output"
```

---

### Task 7: Wire `--shading outline` to HLR in cli.py

**Files:**
- Modify: `brick_icons/cli.py`
- Test: `tests/test_cli.py`

The outline branch must NOT call LDView. It computes segments once and feeds SVG +
mono + gray. Angle comes from `render.resolve_latlong(cfg.angle)`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_cli.py
import shutil as _shutil
HAVE_LIB = (Path("vendor/ldraw")).exists()


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_outline_uses_hlr_not_ldview(tmp_path, monkeypatch):
    called = {"n": 0}
    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("LDView must not be called for outline shading")
    monkeypatch.setattr(cli.render, "render_part", boom)
    rc = cli.main(["3701", "--shading", "outline", "--format", "both",
                   "--mode", "both", "--out", str(tmp_path)])
    assert rc == 0 and called["n"] == 0
    assert (tmp_path / "3701.svg").read_text().count("<line") > 50
    assert Image.open(tmp_path / "3701.mono.png").mode == "1"
    assert (tmp_path / "3701.gray.png").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py -k outline_uses_hlr -v`
Expected: FAIL (LDView still called / outputs wrong).

- [ ] **Step 3: Write minimal implementation**

In `brick_icons/cli.py`: add `from . import render, process, trace, hlr` (add `hlr`). Replace the body of `process_one` so outline is handled first and skips rendering. New `process_one`:

```python
def process_one(cfg: Config, part: str, out_dir: Path, debug_dir=None) -> None:
    name = Path(part).stem if Path(part).suffix else part
    out_dir.mkdir(parents=True, exist_ok=True)

    if cfg.shading == "outline":
        lat, long = render.resolve_latlong(cfg.angle)
        segs, bbox = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                          render_px=cfg.render_px)
        if cfg.fmt in ("svg", "both"):
            fit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
            trace.segments_to_svg(fit, cfg.width, cfg.height, out_dir / f"{name}.svg",
                                  line_px=cfg.line_width, sil_px=cfg.silhouette_width)
        if cfg.fmt in ("png", "both"):
            if cfg.mode in ("gray", "both"):
                gpx = max(cfg.width, cfg.height, cfg.render_px // 2)
                gfit = hlr.fit_segments(segs, bbox, gpx, gpx, cfg.margin, cfg.scale)
                ratio = gpx / max(cfg.width, cfg.height)
                process.draw_segments(gfit, gpx, gpx,
                                      line_px=cfg.line_width * ratio,
                                      sil_px=cfg.silhouette_width * ratio
                                      ).save(out_dir / f"{name}.gray.png")
            if cfg.mode in ("mono", "both"):
                mfit = hlr.fit_segments(segs, bbox, cfg.width, cfg.height, cfg.margin, cfg.scale)
                process.segments_mono(mfit, cfg.width, cfg.height,
                                      line_px=cfg.line_width, sil_px=cfg.silhouette_width
                                      ).save(out_dir / f"{name}.mono.png")
        print(f"done: {part}")
        return

    # --- LDView path (cel / normal / color) ---
    render_png = (_stage(debug_dir, "render", name) if debug_dir
                  else out_dir / f"{name}.render.png")
    render.render_part(cfg, part, render_png)
    rgba = Image.open(render_png).convert("RGBA")

    if cfg.fmt in ("svg", "both"):
        if cfg.shading == "cel":
            trace.cel_svg(rgba, out_dir / f"{name}.svg", levels=cfg.cel_levels)
        else:
            print(f"skip svg for {name}: --shading must be outline or cel (got {cfg.shading})")

    if cfg.fmt in ("png", "both"):
        tone = _tone(cfg, rgba)
        if debug_dir:
            tone.save(_stage(debug_dir, "tone", name))
        if cfg.mode == "color":
            process.flatten_rgb(rgba).save(out_dir / f"{name}.color.png")
        if cfg.mode in ("gray", "both"):
            tone.save(out_dir / f"{name}.gray.png")
        if cfg.mode in ("mono", "both"):
            fitted = process.fit_contain(tone, cfg.width, cfg.height, cfg.margin, cfg.scale)
            mono = process.dither(fitted, cfg.dither, cfg.threshold)
            if debug_dir:
                mono.save(_stage(debug_dir, "mono", name))
            mono.save(out_dir / f"{name}.mono.png")

    if not debug_dir and render_png.exists():
        render_png.unlink()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli.py -k outline_uses_hlr -v`
Expected: PASS (or skip if no library — then verify manually in Task 9).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/cli.py tests/test_cli.py
git commit -m "feat(cli): route --shading outline through HLR (no LDView)"
```

---

### Task 8: Retire the old LDView raster outline

**Files:**
- Modify: `brick_icons/process.py`, `brick_icons/trace.py`, `tests/test_process.py`, `tests/test_cli.py`

- [ ] **Step 1: Delete dead outline code**

Remove from `brick_icons/process.py`: `_dilate`, `_resize_ink`, `outline_masks`,
`_compose_lines`, `make_outline`, `contain_factor`, `outline_mono` (the entire HLR-superseded
block added on 2026-06-27). Keep `_silhouette_mask` (used by `trace.cel_svg`).

Remove from `brick_icons/trace.py`: `outline_svg`.

- [ ] **Step 2: Delete the now-obsolete tests**

In `tests/test_process.py` remove: `_framed_rgba`, `test_make_outline_*`,
`test_contain_factor_*`, `test_outline_mono_*`.
In `tests/test_cli.py` remove: `test_outline_silhouette_width_flag_thickens`,
`test_svg_outline` (the old potrace-outline test). Keep `test_svg_requires_vector_shading`.
In `tests/test_trace.py` remove: `test_outline_svg_*` (potrace outline tests).

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, no references to removed symbols (no ImportError/AttributeError).

- [ ] **Step 4: Grep for stragglers**

Run: `grep -rn "make_outline\|outline_svg\|outline_mono\|outline_masks\|contain_factor" brick_icons tests`
Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add brick_icons tests
git commit -m "refactor: retire LDView raster-trace outline (replaced by HLR)"
```

---

### Task 9: Artifact verification, README, finalize

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Render the 3 spike parts via the real CLI**

Run:
```bash
.venv/bin/python -m brick_icons.cli 3001 3941 3701 --shading outline \
  --format both --mode both --out out/hlr-final
open out/hlr-final/3941.svg out/hlr-final/3941.mono.png
```
Expected: 3941 cylinder silhouette is continuous (no mid-body dropout / stray line);
studs/holes smooth; no stud-apex nub. If 3941 still drops out, raise `SIL_BIAS` in
`hlr.py` (e.g. 0.03 → 0.05) and re-render until the silhouette is solid.

- [ ] **Step 2: Render the full curated list and eyeball**

Run:
```bash
.venv/bin/python -m brick_icons.cli --list parts.txt --shading outline \
  --format both --mode both --out out/hlr-batch
```
Expected: all 24 produce `.svg` + `.mono.png` + `.gray.png`; spot-check 5-6 parts.

- [ ] **Step 3: Update README**

In `README.md`, change the Shading line and Notes to reflect HLR:
- Shading: `outline` is now "vector hidden-line removal from LDraw geometry (no LDView); `--no-outline-interior` removed — interior edges are inherent."
- Note that outline shading does not require LDView/Rosetta.

(Apply the edits; remove the now-false `--no-outline-interior` mention if present.)

- [ ] **Step 4: Run full suite once more**

Run: `.venv/bin/pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: README outline section -> HLR; verify artifacts fixed"
```

---

## Self-Review notes

- **Spec coverage:** parse+flatten (T1), camera (T2), z-buffer HLR + conditional rule (T3), pipeline + silhouette-bias fix + stud-apex skip (T4), mono/gray raster (T5), SVG (T6), cli routing without LDView (T7), retire old path (T8), artifact verification + README + design-reversal already in spec (T9). `--outline-interior` flag: the `--no-outline-interior` CLI flag becomes a no-op for HLR; T9 documents its removal from README. If desired, drop the argparse flag in T8 — left in place is harmless (ignored).
- **Type consistency:** segment tuple `(x1,y1,x2,y2,kind)` and `kind in {"edge","sil"}` used uniformly across `hlr`, `process.draw_segments/segments_mono`, `trace.segments_to_svg`. `visible_segments(part, ldraw_dir, lat, long, render_px)` and `fit_segments(segs, bbox, W, H, margin, scale)` signatures match their call sites in T7.
- **Placeholders:** none — all steps carry complete code/commands.
