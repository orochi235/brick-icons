# Mesh-repair (winding) + analytic HSR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `flat3` base slivers at their root by giving every triangle correct outward-facing winding (cached mesh-repair pass) and by extending depth-HSR to analytic interior faces.

**Architecture:** `flatten` learns to track LDraw BFC state and emits a per-triangle `(certified, invert)` meta list alongside `out["tri"]`. A new `repair.py` turns raw tris into outward-oriented tris — using BFC where certified, a ray-cast outside-test fallback where not — and caches the result to `.cache/mesh/`. `faces_from_tris` then culls true back-faces instead of flipping them. Separately, `cull_occluded_faces` gains a self-depth-at-centroid test so it can also cull occluded analytic faces without a curved face culling itself.

**Tech Stack:** Python 3, numpy, pytest. LDraw part files under `vendor/ldraw`. Reference spec: `docs/superpowers/specs/2026-07-04-mesh-repair-design.md`.

---

## File structure

- `brick_icons/hlr.py` — `flatten` gains BFC parsing + `out["tri_meta"]`; `visible_segments` calls repair; `_visible_segments_analytic` passes own-occluder linkage to the cull. `SIGN_Z`, `view_basis`, `project` unchanged.
- `brick_icons/repair.py` — **new.** `repaired_tris()`, ray-cast crossing helper, disk cache.
- `brick_icons/shade.py` — `faces_from_tris` culls (no flip); `faces_from_analytic` tags faces with their source rec; `cull_occluded_faces` uses self-depth + own-occluder exclusion.
- `tests/test_repair.py` — **new.** BFC + ray-cast + cache unit tests.
- `tests/test_hlr.py`, `tests/test_shade.py` — extend for BFC meta, cull-not-flip, analytic HSR.
- `.gitignore` — add `.cache/`.

Conventions to preserve (verified in code):
- `project(P) = (P@right, -(P@up), P@fwd)`; **depth = P@fwd; smaller depth = nearer the camera.**
- A tri is camera-facing when its view-space normal `nv[2] < 0`.
- LDraw is right-handed with Y-down; **CCW winding (seen from outside) ⇒ `cross(v1-v0, v2-v0)` points outward.**
- `out["tri"]` stays a list of `(3,3)` world-coord arrays; add a **parallel** `out["tri_meta"]` list so existing consumers (`TriangleOccluder`, `_fit_params`) are untouched.

---

## Task 1: BFC state tracking in `flatten`

Parse `0 BFC` meta and carry a winding-invert flag through the recursion, emitting `(certified, invert)` per triangle. `invert=True` means "reverse this tri's stored winding to make it outward-CCW." `certified=False` means "this subfile had no BFC certification — trust ray-cast instead."

**Files:**
- Modify: `brick_icons/hlr.py:36-73` (`flatten`)
- Test: `tests/test_hlr.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_hlr.py`:

```python
def test_flatten_populates_tri_meta_parallel_to_tri(tmp_path):
    from brick_icons import hlr
    import numpy as np
    # A minimal certified part: one CCW triangle, no subfiles.
    p = tmp_path / "cert.dat"
    p.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(p, np.eye(3), np.zeros(3), out, [tmp_path])
    assert len(out["tri"]) == 1
    assert len(out["tri_meta"]) == 1
    assert out["tri_meta"][0] == {"certified": True, "invert": False}


def test_flatten_uncertified_marks_meta(tmp_path):
    from brick_icons import hlr
    import numpy as np
    p = tmp_path / "plain.dat"          # no BFC line at all
    p.write_text("3 16 0 0 0 10 0 0 0 10 0\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(p, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["certified"] is False


def test_flatten_invertnext_flips_winding_flag(tmp_path):
    from brick_icons import hlr
    import numpy as np
    child = tmp_path / "child.dat"
    child.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    parent = tmp_path / "parent.dat"
    parent.write_text(
        "0 BFC CERTIFY CCW\n"
        "0 BFC INVERTNEXT\n"
        "1 16 0 0 0 1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True     # INVERTNEXT toggled it


def test_flatten_negative_determinant_flips_winding_flag(tmp_path):
    from brick_icons import hlr
    import numpy as np
    child = tmp_path / "child.dat"
    child.write_text("0 BFC CERTIFY CCW\n3 16 0 0 0 10 0 0 0 10 0\n")
    parent = tmp_path / "parent.dat"       # mirror on X: det < 0
    parent.write_text(
        "0 BFC CERTIFY CCW\n"
        "1 16 0 0 0 -1 0 0 0 1 0 0 0 1 child.dat\n")
    out = {"2": [], "5": [], "tri": [], "analytic": []}
    hlr.flatten(parent, np.eye(3), np.zeros(3), out, [tmp_path])
    assert out["tri_meta"][0]["invert"] is True     # reflection toggled it
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -k tri_meta -x -q`
Expected: FAIL — `KeyError: 'tri_meta'` / assertion errors (flatten doesn't populate meta yet).

- [ ] **Step 3: Implement BFC tracking in `flatten`**

Replace the body of `flatten` (hlr.py:36-73). Add signature params `winding_cw` and `invert` with defaults, and a per-file BFC scan. Full new function:

```python
def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0,
            inherited_invert: bool = False) -> None:
    if depth > 30:
        return
    out.setdefault("tri_meta", [])
    # Reflection in the accumulated basis flips winding; combine with any
    # INVERTNEXT inherited from the parent reference.
    reflected = bool(np.linalg.det(R) < 0)
    base_invert = inherited_invert ^ reflected
    lines = _lines(path)
    certified = any(_bfc_certified(ln) for ln in lines)
    local_cw = False            # CCW is the LDraw default winding
    invert_next = False
    for ln in lines:
        tok = ln.split()
        if not tok:
            continue
        typ = tok[0]
        if typ == "0":
            cmd = tok[1:]
            if len(cmd) >= 2 and cmd[0] == "BFC":
                flags = cmd[1:]
                if "CW" in flags:
                    local_cw = True
                if "CCW" in flags:
                    local_cw = False
                if "INVERTNEXT" in flags:
                    invert_next = True
            continue
        if typ == "1" and len(tok) >= 15:
            x, y, z = map(float, tok[2:5])
            a, b, c, d, e, f, g, h, i = map(float, tok[5:14])
            M = np.array([[a, b, c], [d, e, f], [g, h, i]], float)
            T = np.array([x, y, z], float)
            ref = " ".join(tok[14:])
            Rsub, tsub = R @ M, R @ T + t
            spec = primitives.parse_primitive(ref)
            if spec is not None and "analytic" in out:
                kind, sector, inner = spec
                out["analytic"].append(
                    {"kind": kind, "sector": sector, "inner": inner,
                     "R": Rsub, "t": tsub})
            else:
                sub = resolve(ref, roots)
                if sub is not None:
                    flatten(sub, Rsub, tsub, out, roots, depth + 1,
                            inherited_invert=base_invert ^ invert_next)
            invert_next = False
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
        elif typ in ("3", "4"):
            n = 3 if typ == "3" else 4
            if len(tok) >= 2 + 3 * n:
                pts = np.array(list(map(float, tok[2:2 + 3 * n])), float).reshape(n, 3) @ R.T + t
                tri_invert = base_invert ^ local_cw
                meta = {"certified": certified, "invert": tri_invert}
                if n == 3:
                    out["tri"].append(pts)
                    out["tri_meta"].append(dict(meta))
                else:
                    out["tri"].append(pts[[0, 1, 2]])
                    out["tri_meta"].append(dict(meta))
                    out["tri"].append(pts[[0, 2, 3]])
                    out["tri_meta"].append(dict(meta))
```

Add the helper above `flatten`:

```python
def _bfc_certified(ln: str) -> bool:
    """True if a line certifies BFC winding ('0 BFC CERTIFY ...' or a bare
    '0 BFC CW|CCW' orientation statement — either establishes trusted winding)."""
    tok = ln.split()
    if len(tok) >= 3 and tok[0] == "0" and tok[1] == "BFC":
        flags = tok[2:]
        if "NOCERTIFY" in flags:
            return False
        return "CERTIFY" in flags or "CW" in flags or "CCW" in flags
    return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -k tri_meta -x -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full hlr suite for regressions**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -q`
Expected: PASS (existing tests unaffected — `out["tri"]` shape unchanged).

- [ ] **Step 6: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "feat(hlr): track LDraw BFC winding state in flatten

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 2: Ray-cast crossing helper (fallback orientation)

A pure function that counts how many triangles a ray crosses at positive distance. Used by the uncertified fallback: shoot along a tri's outward-candidate normal from just outside its centroid; **odd crossings ⇒ that normal points inward ⇒ the tri must be flipped.**

**Files:**
- Create: `brick_icons/repair.py`
- Test: `tests/test_repair.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repair.py`:

```python
import numpy as np
from brick_icons import repair


def _unit_tetra():
    """A small closed tetrahedron (4 tris) around the origin, CCW-outward."""
    v = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]], float)
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    return np.array([[v[a], v[b], v[c]] for a, b, c in faces], float)


def test_ray_crossings_counts_forward_hits():
    tris = _unit_tetra()
    # A ray from far outside on +X pointing back through the solid crosses 2 faces.
    origin = np.array([10.0, 0.0, 0.0])
    direction = np.array([-1.0, 0.0, 0.0])
    assert repair.ray_crossings(origin, direction, tris) == 2


def test_ray_crossings_from_inside_is_odd():
    tris = _unit_tetra()
    origin = np.array([0.0, 0.0, 0.0])          # centroid, inside
    direction = np.array([1.0, 0.0, 0.0])
    assert repair.ray_crossings(origin, direction, tris) % 2 == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_repair.py -k ray_crossings -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'brick_icons.repair'`.

- [ ] **Step 3: Implement `repair.py` with the crossing helper**

Create `brick_icons/repair.py`:

```python
"""Mesh-repair: give every triangle correct outward-facing winding.

Two tiers (see docs/superpowers/specs/2026-07-04-mesh-repair-design.md):
- certified tris: orient directly from the BFC `invert` flag flatten computed;
- uncertified tris: ray-cast outside test (count mesh crossings along the
  candidate normal; odd crossings => normal points inward => flip).

Repair is view-independent and cached to .cache/mesh/ keyed by a content hash
of the raw flatten output.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np


def ray_crossings(origin, direction, tris, eps=1e-7) -> int:
    """Number of triangles in `tris` (shape (M,3,3)) that the ray
    origin + lambda*direction crosses at lambda > eps. Möller-style plane +
    barycentric test; degenerate/parallel hits are skipped."""
    O = np.asarray(origin, float)
    D = np.asarray(direction, float)
    count = 0
    for tri in tris:
        v0, v1, v2 = tri
        e0, e1 = v1 - v0, v2 - v0
        n = np.cross(e0, e1)
        denom = float(D @ n)
        if abs(denom) < 1e-12:
            continue                          # parallel to the triangle plane
        lam = float((v0 - O) @ n) / denom
        if lam <= eps:
            continue                          # behind or at the origin
        P = O + lam * D
        e2 = P - v0
        d00 = float(e0 @ e0); d01 = float(e0 @ e1); d11 = float(e1 @ e1)
        d20 = float(e2 @ e0); d21 = float(e2 @ e1)
        denb = d00 * d11 - d01 * d01
        if abs(denb) < 1e-18:
            continue
        b = (d11 * d20 - d01 * d21) / denb
        w = (d00 * d21 - d01 * d20) / denb
        u = 1.0 - b - w
        if u >= -1e-9 and b >= -1e-9 and w >= -1e-9:
            count += 1
    return count
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_repair.py -k ray_crossings -x -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/repair.py tests/test_repair.py
git commit -m "feat(repair): ray-mesh crossing count for outside test

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 3: Orient tris (BFC + fallback) and cache to disk

`repaired_tris(tri, tri_meta, cache_dir)` returns an oriented `(N,3,3)` array whose stored winding is outward-CCW. Certified tris apply their `invert` flag; uncertified tris use `ray_crossings`. Result is cached by a content hash of the raw input.

**Files:**
- Modify: `brick_icons/repair.py`
- Test: `tests/test_repair.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_repair.py`:

```python
def _outward(tri, centroid):
    n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    return float(n @ (tri.mean(axis=0) - centroid)) > 0


def test_repaired_tris_certified_uses_invert_flag(tmp_path):
    tris = _unit_tetra()
    centroid = tris.reshape(-1, 3).mean(axis=0)
    # Deliberately reverse two faces and flag them invert=True; repair must
    # restore outward winding for ALL faces.
    raw = [t.copy() for t in tris]
    meta = [{"certified": True, "invert": False} for _ in tris]
    raw[0] = raw[0][[0, 2, 1]]; meta[0]["invert"] = True
    raw[3] = raw[3][[0, 2, 1]]; meta[3]["invert"] = True
    fixed = repair.repaired_tris(np.array(raw), meta, cache_dir=tmp_path)
    assert all(_outward(t, centroid) for t in fixed)


def test_repaired_tris_uncertified_uses_raycast(tmp_path):
    tris = _unit_tetra()
    centroid = tris.reshape(-1, 3).mean(axis=0)
    raw = [t.copy() for t in tris]
    raw[1] = raw[1][[0, 2, 1]]           # inward-wound, no trustworthy flag
    meta = [{"certified": False, "invert": False} for _ in tris]
    fixed = repair.repaired_tris(np.array(raw), meta, cache_dir=tmp_path)
    assert all(_outward(t, centroid) for t in fixed)


def test_repaired_tris_cache_hit_skips_recompute(tmp_path):
    tris = _unit_tetra()
    meta = [{"certified": True, "invert": False} for _ in tris]
    a = repair.repaired_tris(tris, meta, cache_dir=tmp_path)
    files = list(tmp_path.glob("*.npz"))
    assert len(files) == 1                # wrote one cache entry
    b = repair.repaired_tris(tris, meta, cache_dir=tmp_path)   # second call
    assert np.array_equal(a, b)
    assert list(tmp_path.glob("*.npz")) == files   # no new file written
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_repair.py -k repaired_tris -x -q`
Expected: FAIL — `AttributeError: module 'brick_icons.repair' has no attribute 'repaired_tris'`.

- [ ] **Step 3: Implement `repaired_tris` + cache**

Append to `brick_icons/repair.py`:

```python
CACHE_VERSION = 1


def _cache_key(tris, tri_meta) -> str:
    h = hashlib.sha1()
    h.update(np.ascontiguousarray(tris, dtype=np.float32).tobytes())
    flags = np.array([[m["certified"], m["invert"]] for m in tri_meta], bool)
    h.update(flags.tobytes())
    h.update(bytes([CACHE_VERSION]))
    return h.hexdigest()[:16]


def _orient(tris, tri_meta):
    tris = np.asarray(tris, float).copy()
    if len(tris) == 0:
        return tris
    for k, m in enumerate(tri_meta):
        if m["certified"]:
            flip = m["invert"]
        else:                                   # ray-cast outside test
            tri = tris[k]
            n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            ln = float(np.linalg.norm(n))
            if ln < 1e-12:
                continue                        # degenerate: leave as-is
            n = n / ln
            c = tri.mean(axis=0)
            # jitter the direction slightly to dodge edge/vertex grazes
            d = n + 1e-4 * np.array([0.113, -0.071, 0.047])
            others = np.concatenate([tris[:k], tris[k + 1:]]) if len(tris) > 1 else tris[:0]
            flip = ray_crossings(c + 1e-5 * n, d, others) % 2 == 1
        if flip:
            tris[k] = tris[k][[0, 2, 1]]
    return tris


def repaired_tris(tris, tri_meta, cache_dir):
    """Outward-oriented (N,3,3) tris. Cached under cache_dir/<key>.npz."""
    tris = np.asarray(tris, float)
    if len(tris) == 0:
        return tris
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(tris, tri_meta)
    fp = cache_dir / f"{key}.npz"
    if fp.exists():
        return np.load(fp)["tris"]
    fixed = _orient(tris, tri_meta)
    np.savez(fp, tris=np.ascontiguousarray(fixed, dtype=np.float32))
    return fixed
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_repair.py -k repaired_tris -x -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/repair.py tests/test_repair.py
git commit -m "feat(repair): orient tris via BFC/raycast + disk cache

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 4: `faces_from_tris` culls back-faces (drop the flip hack); wire repair in

Now that winding is trustworthy, `faces_from_tris` culls a triangle whose outward normal points away from the camera instead of flipping it. `visible_segments` repairs `out["tri"]` before dispatching to either renderer.

**Files:**
- Modify: `brick_icons/shade.py:224-243` (`faces_from_tris`)
- Modify: `brick_icons/hlr.py` (`visible_segments`, ~343-351)
- Test: `tests/test_shade.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shade.py`:

```python
def test_faces_from_tris_culls_backface_no_flip():
    """A triangle whose outward normal points AWAY from the camera is dropped,
    not flipped up into a bright top tone. Winding is now trusted."""
    import numpy as np
    from brick_icons import shade, hlr
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    # Build a tri whose geometric normal points along +fwd (away from camera).
    # cross(v1-v0, v2-v0) should be ~ +fwd.
    v0 = np.zeros(3)
    v1 = right * 10.0
    v2 = np.cross(fwd, right) * 10.0        # so cross(v1,v2) ∝ fwd
    tri = np.array([[v0, v1, v2]], float)
    n = np.cross(v1 - v0, v2 - v0); n /= np.linalg.norm(n)
    assert n @ fwd > 0.5                      # confirm it's a back-face
    faces = shade.faces_from_tris(tri, right, up, fwd, s=2.0, cx=0, cy=0, half=50.0)
    assert faces == []                        # culled, not flipped
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py -k backface_no_flip -x -q`
Expected: FAIL — current code flips the back-face and returns 1 face.

- [ ] **Step 3: Rewrite `faces_from_tris` to cull**

Replace `faces_from_tris` (shade.py:224-243):

```python
def faces_from_tris(tri, right, up, fwd, s, cx, cy, half):
    """Camera-facing triangle faces as px-space polygons with outward view-space
    normals. Winding is trusted (repaired upstream): a triangle whose outward
    normal points away from the camera (nv[2] >= 0) is a back-face and is
    CULLED — never flipped. Flipping was the old hack that leaked bright
    top-tone slivers from hollow parts' undersides."""
    faces = []
    for v in tri:                       # v: (3,3) world coords, outward-CCW
        n = np.cross(v[1] - v[0], v[2] - v[0])
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n = n / ln
        nv = np.array([n @ right, n @ up, n @ fwd])
        if nv[2] > -1e-6:
            continue                    # back-facing or edge-on: cull
        px, py, z = _project_px(v, right, up, fwd, s, cx, cy, half)
        poly = np.stack([px, py], axis=1)
        faces.append({"poly": poly, "normal": nv, "depth": float(np.mean(z)),
                      "kind": "tri"})
    return faces
```

- [ ] **Step 4: Run the shade suite**

Run: `.venv/bin/python -m pytest tests/test_shade.py -x -q`
Expected: PASS. (`test_faces_from_tris_culls_back_and_projects` still holds — it already tolerates 0 or 1 faces.)

- [ ] **Step 5: Wire repair into `visible_segments`**

In `brick_icons/hlr.py`, add near the top-level imports (the module already does `from . import primitives`):

```python
from . import repair
```

Add a module constant next to `SIGN_Z`:

```python
MESH_CACHE_DIR = Path(".cache/mesh")
```

Replace the body of `visible_segments` (hlr.py:343-351) so repair runs before dispatch:

```python
def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900):
    roots = default_roots(ldraw_dir)
    path = _resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    flatten(path, np.eye(3), np.zeros(3), out, roots)
    if out["tri"]:
        fixed = repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                     MESH_CACHE_DIR)
        out["tri"] = [fixed[k] for k in range(len(fixed))]
    right, up, fwd = view_basis(lat, long)
    if out["analytic"]:
        return _visible_segments_analytic(out, right, up, fwd, render_px)
    return _visible_segments_faceted(out, right, up, fwd, render_px)
```

- [ ] **Step 6: Run to verify wiring passes**

Run: `.venv/bin/python -m pytest tests/test_hlr.py tests/test_shade.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py brick_icons/hlr.py tests/test_shade.py
git commit -m "feat(shade): cull back-faces via repaired winding; wire repair pass

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 5: Analytic HSR — self-depth-at-centroid in `cull_occluded_faces`

Extend the cull to analytic faces. A curved face's stored `depth` is a band mean, so compare against the face's **own-occluder depth at its centroid** (self-depth) and exclude the own-occluder from the "nearer?" scan.

**Files:**
- Modify: `brick_icons/shade.py` (`cull_occluded_faces`, `faces_from_analytic`)
- Modify: `brick_icons/hlr.py:322-324` (`_visible_segments_analytic`)
- Test: `tests/test_shade.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_shade.py`:

```python
def test_cull_self_depth_keeps_own_curved_face():
    """A curved wall face must NOT cull itself: with self-depth taken from its
    OWN occluder at the centroid (not the band mean), and the own-occluder
    excluded from the scan, an isolated wall survives."""
    import numpy as np
    from brick_icons import shade

    class FakeOcc:                       # returns a fixed near depth at any ray
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(1.0)                   # wall's near surface at depth 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}        # band MEAN is 5.0 (farther)
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own], ray_origin=ray_origin, fwd=np.array([0, 0, 1.0]),
        eps=1e-3, kinds=("tri", "disc", "ring", "cyli"),
        own_occ={id(face): own})
    assert kept == [face]               # not culled by its own near surface


def test_cull_self_depth_removes_occluded_interior_face():
    import numpy as np
    from brick_icons import shade

    class FakeOcc:
        def __init__(self, d): self.d = d
        def depth(self, O, F): return np.array([self.d], float)

    own = FakeOcc(5.0)                   # interior tube near surface at 5.0
    wall = FakeOcc(1.0)                  # outer wall nearer, at 1.0
    face = {"poly": np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float),
            "depth": 5.0, "kind": "cyli"}
    def ray_origin(xs, ys): return np.zeros((len(xs), 3))
    kept = shade.cull_occluded_faces(
        [face], occluders=[own, wall], ray_origin=ray_origin,
        fwd=np.array([0, 0, 1.0]), eps=1e-3,
        kinds=("tri", "disc", "ring", "cyli"), own_occ={id(face): own})
    assert kept == []                   # outer wall occludes it -> culled
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade.py -k self_depth -x -q`
Expected: FAIL — `cull_occluded_faces` has no `own_occ` param / uses stored depth.

- [ ] **Step 3: Rewrite `cull_occluded_faces`**

Replace the existing `cull_occluded_faces` in `shade.py` with:

```python
def cull_occluded_faces(faces, occluders, ray_origin, fwd, eps,
                        kinds=("tri",), own_occ=None):
    """Winding-independent hidden-surface removal for fill faces.

    A face is culled when another occluder is nearer than the face's own
    surface at its centroid (self_depth) by more than eps. self_depth is:
      - tri faces: the stored mean depth (== centroid depth; planar, exact);
      - analytic faces: the face's OWN occluder depth at the centroid ray
        (a band's mean depth is not its surface depth, so the mean would make a
        curved wall cull itself).
    The own occluder is excluded from the 'nearer?' scan; the -eps margin keeps
    coplanar neighbours (studs/tops sitting ON the plane) from culling a face.

    `own_occ` maps id(face) -> its occluder (analytic faces only). Faces whose
    kind is not in `kinds` pass through untouched."""
    kept = []
    kinds = set(kinds)
    own_occ = own_occ or {}
    for f in faces:
        if f.get("kind") not in kinds:
            kept.append(f)
            continue
        poly = f["poly"]
        ox = np.array([float(poly[:, 0].mean())])
        oy = np.array([float(poly[:, 1].mean())])
        O = ray_origin(ox, oy)
        mine = own_occ.get(id(f))
        if mine is not None:
            self_depth = float(mine.depth(O, fwd)[0])
        else:
            self_depth = f["depth"]
        occluded = False
        for occ in occluders:
            if occ is mine:
                continue                          # don't let a face occlude itself
            d = float(occ.depth(O, fwd)[0])
            if d < self_depth - eps:
                occluded = True
                break
        if not occluded:
            kept.append(f)
    return kept
```

- [ ] **Step 4: Tag analytic faces with their source rec**

In `shade.py`, `faces_from_analytic`: add `"rec": rec` to each appended face dict so `hlr` can map face → occluder. Change the disc/ring append:

```python
            faces.append({"poly": np.stack([px, py], 1), "normal": nv,
                          "depth": float(np.mean(z)), "zs": z, "kind": kind,
                          "rec": rec})
```

and in `_cyl_wall_face`, add `"rec": rec` to the returned dict:

```python
    return {"poly": poly, "zs": zs, "depth": float(np.mean(zs)), "kind": "cyli",
            "rec": rec, "grad_axis": (p0, p1), "grad_samples": samples}
```

(`_cyl_wall_face` already receives `rec` as its first argument.)

- [ ] **Step 5: Wire own-occluder linkage + analytic kinds in `hlr`**

In `_visible_segments_analytic` (hlr.py:322-324), replace:

```python
    faces = shade.faces_from_tris(np.array(out["tri"]), right, up, fwd, s, cx, cy, half) \
        if out["tri"] else []
    faces = shade.cull_occluded_faces(faces, occluders, ray_origin, fwd, eps)
    faces += shade.faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half)
```

with:

```python
    tri_faces = shade.faces_from_tris(np.array(out["tri"]), right, up, fwd, s, cx, cy, half) \
        if out["tri"] else []
    an_faces = shade.faces_from_analytic(analytic, right, up, fwd, s, cx, cy, half)
    own_occ = {id(f): rec_occ.get(id(f["rec"])) for f in an_faces
               if rec_occ.get(id(f["rec"])) is not None}
    faces = shade.cull_occluded_faces(
        tri_faces + an_faces, occluders, ray_origin, fwd, eps,
        kinds=("tri", "disc", "ring", "cyli"), own_occ=own_occ)
```

- [ ] **Step 6: Run the shade + hlr suites**

Run: `.venv/bin/python -m pytest tests/test_shade.py tests/test_hlr.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py brick_icons/hlr.py tests/test_shade.py
git commit -m "feat(shade): analytic HSR via self-depth-at-centroid cull

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Task 6: Gitignore cache + visual regression on specimens

Confirm the slivers are gone on 3001/3020/3941 and that the good specimens are unchanged.

**Files:**
- Modify: `.gitignore`
- No test file (visual check).

- [ ] **Step 1: Ignore the cache dir**

Add a line to `.gitignore`:

```
.cache/
```

- [ ] **Step 2: Render the sliver specimens after the fix**

Run:

```bash
.venv/bin/python -m brick_icons.cli 3001 3020 3941 --format svg \
  --shading outline --shade-style flat3 --out out/slivers-fixed
cd out/slivers-fixed && for f in 3001 3020 3941; do \
  qlmanage -t -s 600 -o . $f.svg >/dev/null 2>&1; done && open *.png
```

Expected: no bright top-tone sliver at the front-bottom edge of any of the three; 3941's base patches gone.

- [ ] **Step 3: Render the "must not regress" specimens**

Run:

```bash
.venv/bin/python -m brick_icons.cli 6143 4589 3960 50950 3040b 3005 \
  --format svg --shading outline --shade-style flat3 --out out/regress
cd out/regress && for f in 6143 4589 3960 50950 3040b 3005; do \
  qlmanage -t -s 600 -o . $f.svg >/dev/null 2>&1; done && open *.png
```

Expected: outer cylinder walls, disc tops, slopes intact — no vanished faces / holes from over-culling.

- [ ] **Step 4: Full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (whole suite).

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore mesh-repair cache dir

$(printf 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')"
```

---

## Self-review notes

- **Spec coverage:** Component 1 (BFC) → Task 1; ray-cast fallback → Tasks 2-3; cache → Task 3; drop flip hack → Task 4; Component 2 analytic HSR → Task 5; `.cache/` gitignore → Task 6; visual regression on specimens → Task 6. All spec sections mapped.
- **Type consistency:** `out["tri_meta"]` entries are `{"certified": bool, "invert": bool}` throughout (Tasks 1, 3). `repaired_tris(tris, tri_meta, cache_dir)` and `ray_crossings(origin, direction, tris)` signatures match between definition (Tasks 2-3) and call site (Task 4). `cull_occluded_faces(..., kinds, own_occ)` matches between definition (Task 5 Step 3) and call (Task 5 Step 5). Analytic faces carry `"rec"` (Task 5 Step 4) consumed by `own_occ` build (Step 5).
- **Fallback correctness:** `_orient` excludes the source triangle from `ray_crossings` and offsets the origin off the surface, so a tri never counts its own plane.
```
