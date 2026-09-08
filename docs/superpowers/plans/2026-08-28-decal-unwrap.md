# Decal Unwrap Implementation Plan (phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Printed parts render their print — the right shapes in the right LDraw colors, sitting flush on the wall they decorate.

**Architecture:** The LDraw color code rides `tri_meta` out of `hlr.flatten` and into each face dict. Both merge paths then refuse to union across a color boundary, which is what currently erases flat prints. A new `brick_icons/unwrap.py` binds each decoration region to an analytic carrier and maps it into that carrier's parameter space; **every carrier goes through it — planar, cylinder and cone — with the planar map as the identity**, so flat never becomes a special case that drifts. The unwrapped region is emitted as a standalone texture artifact, then re-projected onto the exact analytic surface and painted with its resolved color.

**Tech Stack:** Python 3.11+, numpy, shapely, pytest. Spec: `docs/superpowers/specs/2026-08-28-printed-parts-design.md`. Phase 1 (`brick_icons/colors.py`) is committed and supplies `resolve()`.

**Commands:** tests `.venv/bin/python -m pytest -q` (single test with `-k`). Specimens: `.venv/bin/brick-icons --list specimens.txt --root . --format svg --shading outline --shade-style flat3 --out <dir>`. Ground truth: `.venv/bin/python scripts/render-references.py <ids>`.

**Scope note:** this is a large plan with one natural checkpoint. Through Task 7 every print appears in the right color at the authored faceting; Tasks 8–14 put it on the exact carrier surface and turn the meshes back into shapes.

---

## Status: DONE — all tasks landed, branch `decal-uv`

413 tests pass. The 18 unprinted specimens are byte-identical to `main`, and
all four printed specimens match LDView structurally. `3941p01`'s panel emits
as ONE path where it was six separately stroked fragments; `3068bp00` is back
to its baseline 2,676 bytes with the arrow as a single path.

| task | commit |
|---|---|
| 2 color through `flatten` | `7283a36` |
| 3 repair order/cache key pinned | `5014eac` |
| 4 color on face dicts | `24aaaaf` |
| 5 both `shade.py` merges color-aware | `10b1e1a` |
| 6 paint decoration flat | `9ad2e0b` |
| 6b color on analytic primitives | `ca33697` |
| 6c decoration skips gradients | `c970622` |
| 8 bind to a carrier | `a1d4ba4` |
| 9 the unwrap maps | `8a38ec9` |
| 10 texture artifact | `05ce6f4` |
| 11 union in UV | `0e1288d` |
| 12 rounded rects and circles | `260c0f8` |
| 13-14 re-project + gates | `9cd08a0` |

### Where this plan was wrong, and what the data said

Each of these was written into a task above and would have shipped silently.

- **A sector bounds what a primitive DRAWS, not where its surface is.** Task 8
  gated the bind on it; `3941p01`'s r=20 wall is substituted over two 90 deg
  sectors while the panel sits at 125 deg, so nothing bound. Same axis, same
  radius and an overlapping height is the same surface of revolution.
- **A primitive with no HEIGHT bound is infinite.** Panel facets bound to stud
  cylinders 794 LDU away. Measure the gap in the primitive's own frame, where
  the wall is the unit circle — that bounds the extent and makes a cone's
  taper exact instead of matching only where its radius equals `|R[:,0]|`.
- **`arcfit._fit_circle` returns `(C, U, V, t_deg, n_anchors)` on (m,3)
  points**, not `(cx, cy, r)`. Task 12's `fit[0], fit[1], fit[2]` would have
  read vectors as scalars. UV has no camera, so a direct 2-D Kasa fit is both
  simpler and exact; arcfit's terminal anchoring exists for projected chains.
- **Corner radius cannot be measured from where the straight runs end.** An arc
  runs within tolerance of its own tangent line for several vertices either
  side of tangency, reading `3941p01`'s corners as 1.087 against a true 1.261.
  Solve r from each corner vertex: r = a + b + sqrt(2ab).
- **LDraw 0 Black is `#1b2a34`,** not the `#05131d` Task 14 asserts.
- **A decal straddling theta = +-pi splits in two.** Put the branch cut in the
  widest angular gap the decal leaves empty, or `3941p01`'s second panel can
  never merge, fit as one shape, or stroke as one boundary.

### Found by testing, not in the plan at all

- **The cone round trip was not identity** — `to_xyz` mapped every point back
  at the base radius, putting a cone's decal on a cylinder.
- **A plane needs no densification.** Its unwrap is the identity and projection
  is linear, so a straight edge stays straight; densifying anyway inflated
  `3068bp00` from 2,676 to 10,978 bytes.
- **A curved carrier must outrank a plane.** The wall under a decal is
  hand-faceted wherever no primitive was substituted, and each such facet is a
  plane the decoration sits exactly on at gap 0 — matching one would beat the
  cylinder and flatten the curvature the unwrap exists to dissolve.
- **`absorb_wall_facets`' missing color guard is moot for bound decals:** the
  unwrap runs first and a bound decal is already its own region.

---

## Established before writing this plan

Numbers here are measured, not assumed. Don't re-derive them.

- **Root cause:** `hlr.py:62` `flatten()` parses type 1/2/3/4/5 lines and never reads `tok[1]`. Decoration therefore arrives geometrically identical to its carrier. Confirmed against LDView on all four printed specimens: none renders its print.
- **`repair._orient` preserves triangle order and count** (in-place flip per index, `repair.py:74-95`), so an index-parallel color array survives `repaired_tris`. Its cache key hashes only geometry plus `certified`/`invert` — **do not add color to `_cache_key`**; color cannot affect orientation and the change would invalidate every cached mesh.
- **Test triangles must be wound CCW or they vanish.** `faces_from_tris` culls
  back-faces and never flips them, so a fixture triangle written clockwise is
  dropped and the test dies on an index error rather than the assertion it was
  written for. With `FakeProj`'s `fwd = (0, 0, -1)`, CCW in the XY plane means a
  +z normal.
- **Suite counts here are absolute and start from 363.** Each task's expected
  count includes every test added by earlier tasks: 365, 367, 369, 371, 372,
  then the `test_unwrap.py` additions to 392. If a count is off by exactly the
  number of tests an earlier task added, trust the delta and fix the plan.
- **Whole-dict assertions break when you add a key.** `tests/test_hlr.py`
  compares `tri_meta` entries with `==`, and other suites do the same to face
  dicts. Before adding a key to any shared dict, grep for equality assertions
  on it — the plan's expected test counts assume you fixed them in the same task.
- **FOUR merge paths must each learn about color**, and a decal trips whichever
  ones its construction happens to reach. `_attach_smooth_gradients` unions faces
  across a shared edge when normals agree to 0.9999; `_merge_members` unions flat
  faces by `plane` key; `primitives.merge_smooth_walls` collapses full-sector
  cylinder/cone chains; and `absorb_wall_facets` makes facet triangles lying ON an
  analytic wall inherit that wall's gradient and merge into its fill. The last one is
  why `3942bp01`'s cone shows no red: its 160 stripe facets sit exactly on the carrier
  cone at the same radii and each spans 7.5 deg, so every one is absorbed into the body.
  Fixing three of four still leaves prints missing.
- **Binding tolerance is 0.5 LDU** for curved carriers, from `scripts/measure-decal-offsets.py`: `3960p01` 0.001, `3062bp01` 0.006, `3626bp01` 0.011, `3941p01` 0.074, `4740p01` 0.150, `3040bp08` 0.345. No bimodality. There is no outward snap — decal and carrier are already co-radial.
- **The unwrap dissolves authored faceting.** `3941p01`'s panel is 36 hand-written quads forming a 16-gon at r=20 (cos(π/N) = 19.616/20 → N=16); in (θ, h) it is one rounded rectangle. `3942bp01`'s 160 decoration facets are 16 clean rectangles. Prototyped and rendered.
- **The carrier defines the texture canvas, at one uniform scale.** Scaling the decal's own bounding box to a fixed canvas warps it — round lamps become ellipses. Use the carrier's parameter extent and a single scale factor. For a cylinder that means arc length `θ·r`, not degrees.
- **There are TWO geometry paths, and both need every change.** Facet triangles go
  through `hlr.flatten` -> `tri_meta` -> `faces_from_tris`; substituted primitives go
  through `out["analytic"]` -> `faces_from_analytic`. A decal routinely uses both at
  once — `3941p01`'s panel is 36 quads AND 24 primitive pieces — so a change wired to
  only one path yields a half-painted print. Task 6b exists because Tasks 2-6 wired
  only the triangle path.
- **Nothing in LDraw is a curve or a region.** A decal is a mesh: `3068bp00`'s arrow is 11 triangles, `3040bp08`'s border 68 facets, and every "circle" is a 16-gon fan. Both recoveries — union facets into a region, fit a polygon fan back to a circle — belong in UV, because UV has no camera. The existing `arcfit` fights foreshortening (a circle projects to an ellipse) and chord-proxy occlusion; neither exists in UV, so `arcfit._fit_circle` becomes an exact fit rather than a best-effort one.
- **LDView is the reference, structurally not numerically.** `-AllowPrimitiveSubstitution` gates `-CurveQuality` and matches on primitive *filename*, so LDView renders one part at two fidelities — smooth where a stock primitive was referenced, faceted where the author wrote quads. Never pixel-gate against it.

---

### Task 1: Baseline the gate

**Files:** none created in-repo (`debug/` is gitignored).

- [ ] **Step 1: Confirm the suite is green**

Run: `.venv/bin/python -m pytest -q`
Expected: 363 passed. If not, STOP and report — the safety net must be intact first.

- [ ] **Step 2: Snapshot the specimens**

```bash
mkdir -p debug/unwrap
.venv/bin/brick-icons --list specimens.txt --root . --format svg \
  --shading outline --shade-style flat3 --out debug/unwrap/before
cd debug/unwrap && find before -name '*.svg' -exec shasum -a 256 {} + \
  | sed 's|before/||' | sort > before.sha && cd ../..
wc -l debug/unwrap/before.sha
```

Expected: 22 lines.

- [ ] **Step 3: Confirm determinism**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg \
  --shading outline --shade-style flat3 --out debug/unwrap/before2
cd debug/unwrap && find before2 -name '*.svg' -exec shasum -a 256 {} + \
  | sed 's|before2/||' | sort > before2.sha
diff before.sha before2.sha && echo DETERMINISTIC; cd ../..
```

Expected: `DETERMINISTIC`. If hashes differ, STOP — every gate below is worthless without it.

---

### Task 2: Carry the LDraw color out of `flatten`

**Files:**
- Modify: `brick_icons/hlr.py:62-134`
- Test: `tests/test_hlr_color.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hlr_color.py`:

```python
import numpy as np
import pytest

from brick_icons import hlr

PART = """\
0 BFC CERTIFY CCW
4 16 0 0 0 1 0 0 1 0 1 0 0 1
4 14 0 1 0 1 1 0 1 1 1 0 1 1
3 4 0 2 0 1 2 0 1 2 1
"""


@pytest.fixture
def part(tmp_path):
    p = tmp_path / "t.dat"
    p.write_text(PART)
    return p


def test_flatten_records_a_color_per_triangle(part):
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, [part.parent])
    # two quads -> two tris each, one tri -> one: 5 triangles
    assert len(out["tri"]) == 5
    assert len(out["tri_meta"]) == 5
    assert [m["color"] for m in out["tri_meta"]] == [16, 16, 14, 14, 4]


def test_flatten_resolves_color_16_against_the_reference(tmp_path):
    """Color 16 in a subfile inherits the referring line's color."""
    (tmp_path / "sub.dat").write_text("0 BFC CERTIFY CCW\n"
                                      "3 16 0 0 0 1 0 0 1 1 0\n")
    top = tmp_path / "top.dat"
    top.write_text("0 BFC CERTIFY CCW\n"
                   "1 14 0 0 0 1 0 0 0 1 0 0 0 1 sub.dat\n")
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(top, np.eye(3), np.zeros(3), out, [tmp_path])
    assert [m["color"] for m in out["tri_meta"]] == [14]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_hlr_color.py -q`
Expected: FAIL with `KeyError: 'color'`

- [ ] **Step 3: Thread the color through `flatten`**

In `brick_icons/hlr.py`, give `flatten` a `color: int = 16` parameter:

```python
def flatten(path: Path, R: np.ndarray, t: np.ndarray, out: dict,
            roots: list[Path], depth: int = 0,
            inherited_invert: bool = False, color: int = 16) -> None:
```

Inside the `for ln in lines:` loop, right after `typ = tok[0]` and the `typ == "0"` branch, resolve this line's color:

```python
        # LDraw column 2: 16 means "inherit the referring line's color",
        # 24 is the edge color. Anything else overrides.
        own = int(tok[1]) if len(tok) > 1 and tok[1].lstrip("#").isdigit() else 16
        cur = color if own == 16 else own
```

In the `typ == "1"` branch, pass it down — change the recursive call to:

```python
                        flatten(sub, Rsub, tsub, out, roots, depth + 1,
                                inherited_invert=base_invert ^ invert_next
                                ^ m_reflect, color=cur)
```

In the `typ in ("3", "4")` branch, record it in the meta dict:

```python
                meta = {"certified": certified, "invert": tri_invert,
                        "color": cur}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_hlr_color.py -q`
Expected: 2 passed

- [ ] **Step 5: Update the two assertions the new key breaks**

`tests/test_hlr.py` compares whole `tri_meta` entries for equality, so both
of these fail on the added key. Add `"color": 16` to each expected dict (both
fixtures use color 16); the other `tri_meta` assertions index by key and are
unaffected.

```python
    assert out["tri_meta"][0] == {"certified": True, "invert": False,
                                  "color": 16}
```
```python
    assert out["tri_meta"][0] == out["tri_meta"][1] == {
        "certified": True, "invert": False, "color": 16}
```

- [ ] **Step 6: Confirm nothing else broke**

Run: `.venv/bin/python -m pytest -q`
Expected: 365 passed

- [ ] **Step 7: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr_color.py tests/test_hlr.py
git commit -m "carry the LDraw color code through flatten"
```

---

### Task 3: Prove the repair pass keeps color parity

**Files:**
- Test: `tests/test_hlr_color.py` (append)

This is a guard, not a change. `repaired_tris` returns a new array; if it ever reorders, every color index silently shifts and prints paint onto the wrong facets.

- [ ] **Step 1: Write the test**

Append to `tests/test_hlr_color.py`:

```python
from brick_icons import repair


def test_repair_preserves_triangle_order_and_count(tmp_path):
    tris = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[0, 0, 1], [0, 1, 1], [1, 0, 1]],
        [[2, 0, 0], [3, 0, 0], [2, 1, 0]],
    ], float)
    meta = [{"certified": True, "invert": False, "color": c}
            for c in (16, 14, 4)]
    fixed = repair.repaired_tris(tris, meta, tmp_path)
    assert len(fixed) == len(tris)
    # a flip permutes vertices WITHIN a triangle, never triangles themselves,
    # so each output triangle keeps its input's vertex set
    for got, want in zip(fixed, tris):
        assert {tuple(v) for v in np.round(got, 6)} == \
               {tuple(v) for v in np.round(want, 6)}


def test_repair_cache_key_ignores_color(tmp_path):
    """Color cannot affect orientation; keying on it would invalidate every
    cached mesh for no gain."""
    tris = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    a = [{"certified": True, "invert": False, "color": 16}]
    b = [{"certified": True, "invert": False, "color": 4}]
    assert repair._cache_key(tris, a) == repair._cache_key(tris, b)
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_hlr_color.py -q`
Expected: 4 passed. If `test_repair_preserves_triangle_order_and_count` fails, STOP — Tasks 4 onward assume index parity and must be redesigned around an explicit id instead.

- [ ] **Step 3: Commit**

```bash
git add tests/test_hlr_color.py
git commit -m "pin the repair pass's triangle order and cache key"
```

---

### Task 4: Put the color on each face dict

**Files:**
- Modify: `brick_icons/hlr.py:925-935`, `brick_icons/shade.py:1568-1607`
- Test: `tests/test_shade_color.py`

- [ ] **Step 1: Find how `faces_from_tris` is called**

Run: `grep -rn "faces_from_tris" brick_icons/ tests/`
Expected: the definition at `shade.py:1568` plus its call sites. Note each one — every caller needs the new argument.

- [ ] **Step 2: Write the failing test**

Create `tests/test_shade_color.py`:

```python
import numpy as np

from brick_icons import shade


class FakeProj:
    right = np.array([1.0, 0.0, 0.0])
    up = np.array([0.0, 1.0, 0.0])
    fwd = np.array([0.0, 0.0, -1.0])

    def to_px(self, v):
        return v[:, 0] * 10, v[:, 1] * 10, v[:, 2]


def test_faces_carry_their_triangle_color():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[2, 0, 0], [3, 0, 0], [2, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert [f["color"] for f in faces] == [16, 14]


def test_faces_default_to_the_part_color_when_none_given():
    tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
    faces = shade.faces_from_tris(tri, FakeProj())
    assert [f["color"] for f in faces] == [16]
```

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -q`
Expected: FAIL with `TypeError: faces_from_tris() got an unexpected keyword argument 'colors'`

- [ ] **Step 4: Accept and record the color**

In `brick_icons/shade.py`, change the signature at line 1568:

```python
def faces_from_tris(tri, proj, cond_edges=None, colors=None):
```

Change the loop header so the index is available, and default the color:

```python
    for i, v in enumerate(tri):         # v: (3,3) world coords, outward-CCW
        c = 16 if colors is None else int(colors[i])
```

Add `"color": c` to the face dict built at line 1598:

```python
        f = {"poly": poly, "normal": nv, "depth": float(np.mean(z)),
             "zs": z, "kind": "tri", "plane": plane, "_verts": v,
             "color": c}
```

Note: `continue` statements earlier in the loop (degenerate normal, culled
back-face) must stay above the face-dict construction, so `colors` stays
indexed by input triangle, not by output face.

- [ ] **Step 5: Pass the colors from the caller**

In `brick_icons/hlr.py` around line 931, the repaired tris are produced. Carry the meta colors alongside them and hand them to `faces_from_tris` at each call site found in Step 1:

```python
        fixed = repair.repaired_tris(np.array(out["tri"]), out["tri_meta"],
                                     cache_dir)
        out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -q`
Expected: 2 passed

Run: `.venv/bin/python -m pytest -q`
Expected: 369 passed

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py brick_icons/hlr.py tests/test_shade_color.py
git commit -m "put each triangle's LDraw color on its face"
```

---

### Task 5: Stop both merges crossing a color boundary

**Files:**
- Modify: `brick_icons/shade.py:1810-1814`, `brick_icons/shade.py:534-545`
- Test: `tests/test_shade_color.py` (append)

This is the change that makes flat prints appear at all.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shade_color.py`:

```python
def test_coplanar_faces_of_different_colors_do_not_union():
    """A decal quad is coplanar with its carrier and shares an edge with it.
    Unioning them is what erases flat prints today."""
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],      # carrier
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],      # decal, shares an edge
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 14])
    assert faces[0]["group"] != faces[1]["group"]


def test_coplanar_faces_of_the_same_color_still_union():
    tri = np.array([
        [[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        [[1, 0, 0], [1, 1, 0], [0, 1, 0]],
    ], float)
    faces = shade.faces_from_tris(tri, FakeProj(), colors=[16, 16])
    assert faces[0]["group"] == faces[1]["group"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -k colors -q`
Expected: FAIL on `test_coplanar_faces_of_different_colors_do_not_union` — the groups are equal.

- [ ] **Step 3: Guard the edge-adjacency union**

In `_attach_smooth_gradients` (`brick_icons/shade.py`), inside `for ek, ks in by_edge.items():`, refuse the union when the colors differ. Replace the loop body's guard:

```python
        for k in ks[1:]:
            # a decal is coplanar with its carrier and shares its edges;
            # unioning across the color boundary is what erased flat prints
            if faces[ks[0]].get("color", 16) != faces[k].get("color", 16):
                continue
            # union across a seam always; across an ordinary shared edge only
            # when coplanar (quad halves meet at a diagonal, which is never a
            # conditional line) — coplanar union can't cross a real crease
            coplanar = float(faces[ks[0]]["normal"] @ faces[k]["normal"]) > 0.9999
            if ek not in seam_keys and not coplanar:
                continue
```

- [ ] **Step 4: Guard the plane-key union**

In `_merge_members` (`brick_icons/shade.py:534`), the plane key must include the color, or T-junction merging re-joins what Step 3 just separated:

```python
        if (f.get("plane") is not None and "grad_axis" not in f
                and "grad_radial" not in f):
            ra = find(("p", f["plane"], f.get("color", 16)))
            rb = find(keys[idx])
            if ra != rb:
                parent[rb] = ra
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -q`
Expected: 4 passed

Run: `.venv/bin/python -m pytest -q`
Expected: 371 passed

- [ ] **Step 6: See it on a real part**

```bash
.venv/bin/brick-icons 3068bp00 --root . --format svg --shading outline \
  --shade-style flat3 --out debug/unwrap/t5
grep -c '<path' debug/unwrap/t5/3068bp00.svg
```

Expected: more paths than before — the arrow is now its own region rather than merged into the tile top. It will still be the *wrong color* (Task 6 fixes that); this step only proves the region survived the merge.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py tests/test_shade_color.py
git commit -m "keep surface merges from crossing a color boundary"
```

---

### Task 6: Paint each region in its own LDraw color

**Files:**
- Modify: `brick_icons/shade.py:1319`
- Test: `tests/test_shade_color.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shade_color.py`:

```python
from brick_icons import colors as ldcolors


def test_decoration_fills_use_the_ldraw_color(tmp_path):
    """Color 16 takes the part color and shades; anything else paints its
    own LDraw color, so a print reads as print rather than as engraving."""
    face_body = {"normal": np.array([0.0, 0.0, -1.0]), "color": 16}
    face_deco = {"normal": np.array([0.0, 0.0, -1.0]), "color": 4}
    style = shade.Flat3Style(part_color=(157, 157, 157))
    assert shade.face_fill(face_body, style, "vendor/ldraw") == \
        style.tone(face_body["normal"])
    assert shade.face_fill(face_deco, style, "vendor/ldraw").lower() == "#b40000"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -k ldraw_color -q`
Expected: FAIL with `AttributeError: module 'brick_icons.shade' has no attribute 'face_fill'`

- [ ] **Step 3: Add the helper**

In `brick_icons/shade.py`, above `fill_ops`:

```python
def face_fill(face, style, ldraw_dir):
    """A face's fill: shaded part tone for body geometry (color 16), the
    flat LDraw color for decoration. Decoration is print, not relief — tone
    it and it reads as engraving, which is the bug this fixes."""
    code = face.get("color", 16)
    if code == 16:
        return style.tone(face["normal"])
    hex_str, _ = colors.resolve(str(code), ldraw_dir)
    return "#" + hex_str[2:]
```

Add `from . import colors` to the module imports if it is not already there.

- [ ] **Step 4: Use it at the emission site**

`fill_ops` needs the ldraw dir to resolve codes. Add a parameter:

```python
def fill_ops(faces, style, clip=True, ellipses=None, proj=None, fit=None,
             refits=None, loops=None, strokes=None, line_px=2.0,
             sil_px=2.0, drop=None, weld_corners=False, ldraw_dir="vendor/ldraw"):
```

At line 1319, replace `style.tone(f["normal"])`:

```python
            ops.append({"d": d, "fill": face_fill(f, style, ldraw_dir),
```

Then pass `ldraw_dir=cfg.ldraw_dir` at BOTH `fill_ops` call sites in `brick_icons/cli.py` (lines ~145 and ~177 — one per render path). `cfg` is in scope at each.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -q`
Expected: 5 passed

Run: `.venv/bin/python -m pytest -q`
Expected: 372 passed

- [ ] **Step 6: Look at it**

```bash
.venv/bin/python scripts/render-references.py 3068bp00 3040bp08 --out out/t6
open out/t6/references.png
```

Expected: `3068bp00` now shows a yellow arrow and `3040bp08` a yellow border with red squares, matching the LDView half above them. Curved carriers are not fixed yet.

- [ ] **Step 7: Commit**

```bash
git add brick_icons/shade.py brick_icons/cli.py tests/test_shade_color.py
git commit -m "paint decoration in its own LDraw color"
```

---

### Task 6b: Carry the color onto analytic primitives

**Files:**
- Modify: `brick_icons/primitives.py`, `brick_icons/hlr.py`, `brick_icons/shade.py`
- Test: `tests/test_shade_color.py` (append)

**Why this task exists:** Tasks 2-6 wired the TRIANGLE path only. Decoration built from
substituted primitives still paints in body tone, which is measurable in the Task 6
render: `3941p01`'s panel comes out as scattered black patches because its 36 quads
paint but its 8 `1-4chrd` and 16 `4-4ndis` pieces do not; `3942bp01`'s stripes
(`48\5-24co*`) and `3040bp08`'s lamps (`4-4disc`, color 14) do not paint at all.
`hlr.flatten` computes the color and then drops it at
`out["analytic"].append(prim)`, and `faces_from_analytic` never sets one.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shade_color.py`:

```python
def test_analytic_faces_carry_the_primitive_color():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3), color=14)
    faces = shade.faces_from_analytic([disc], proj)
    assert faces, "the disc should produce at least one face"
    assert all(f["color"] == 14 for f in faces)


def test_analytic_primitives_default_to_the_part_color():
    from brick_icons import hlr, primitives as P
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    proj = P.Projection(right, up, fwd, 2.0, 0.0, 0.0, 50.0)
    disc = P.Disc(R=np.diag([4.0, 1.0, 4.0]), t=np.zeros(3))
    faces = shade.faces_from_analytic([disc], proj)
    assert all(f["color"] == 16 for f in faces)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py -k analytic -q`
Expected: FAIL — `Disc` takes no `color` argument.

- [ ] **Step 3: Give `Primitive` a color field**

In `brick_icons/primitives.py`, add to the `Primitive` dataclass beside `sector`:

```python
    sector: float = 360.0
    color: int = 16          # LDraw code; 16 = inherit the part color
```

It is `kw_only=True`, so a defaulted field is safe to add and every subclass inherits it.

- [ ] **Step 4: Attach it in the loader**

In `brick_icons/hlr.py`'s `flatten`, the type-1 branch already computes `cur`. Set it
on the primitive before appending:

```python
                prim = primitives.from_ref(ref, Rsub, tsub)
                if prim is not None and "analytic" in out:
                    prim.color = cur
                    out["analytic"].append(prim)
```

- [ ] **Step 5: Stamp it on the faces**

In `brick_icons/shade.py`:

```python
def faces_from_analytic(analytic, proj):
    """Fill faces for analytic primitives, with smooth wall chains merged to
    single faces (see primitives.merge_smooth_walls)."""
    out = []
    for prim in primitives.merge_smooth_walls(analytic):
        for f in prim.faces(proj):
            f.setdefault("color", getattr(prim, "color", 16))
            out.append(f)
    return out
```

- [ ] **Step 6: Keep the wall merge from crossing a color boundary**

`merge_smooth_walls` collapses chains of full-sector cylinders/cones into one synthetic
primitive. Add the color to its `by_key` grouping key so a colored wall never merges
into a body one — the same rule Task 5 applied to the other two merges. Find the
`by_key[...]` line and append `p.color` to the key tuple. The synthetic primitive it
builds must carry that color too.

Note: this is a guard, not a fix for a part we have — `3942bp01`'s stripes are
5/24 sectors, so `is_full` is False and they never reach this merge. Add it anyway;
leaving a third color-blind merge in place is how this class of bug returns.

- [ ] **Step 7: Run the targeted tests**

Run: `.venv/bin/python -m pytest tests/test_shade_color.py tests/test_shade.py tests/test_hlr.py tests/test_hlr_color.py tests/test_primitives.py -q`
Expected: all pass.

- [ ] **Step 8: Look at it**

```bash
.venv/bin/python scripts/render-references.py 3941p01 3942bp01 3040bp08 --out out/t6b
```

Expected: `3941p01`'s panel is now a solid black region rather than patches;
`3942bp01` shows red stripes; `3040bp08`'s lamps are yellow rather than empty circles.
Report the script's final lines. Do NOT run `open`.

- [ ] **Step 9: Commit**

```bash
git add brick_icons/primitives.py brick_icons/hlr.py brick_icons/shade.py \
        tests/test_shade_color.py
git commit -m "carry the LDraw color onto analytic primitives"
```

---

### Task 6c: Decoration takes no shading ramp — DONE (`c970622`)

**Recorded because the original text of this task was wrong.** It claimed
`3942bp01`'s cone showed no red because `absorb_wall_facets` swallowed its 160
stripe facets into the carrier wall's gradient. That diagnosis was false: the
stripes reach the pipeline as `Cone` PRIMITIVES, not facets. `48\5-24co10.dat`
is a `~Moved to` redirect, which `flatten` follows, inheriting color 4 through
it, so `hlr.flatten` yields 16 `Cone` primitives at color 4 and ZERO decoration
triangles. There was nothing for wall absorption to absorb.

The real cause: `fill_ops` has three emission branches, and only the flat `else`
called `face_fill`. Both gradient branches — `grad_radial` via
`_radial_focal_stops`, and `grad_axis` via the inline `style.ramp(nv)` sort —
tone from the body part color and never read `face["color"]`. Every curved
surface shades with a gradient, so ALL decoration on a cylinder or cone painted
in body tone. The fix routes decoration to the flat branch: a print is ink on a
surface, not relief, so it takes no shading ramp.

A follow-on landed with it (`ba688d5`): the edge-adjacency union required
coplanarity or a conditional-line seam, and `3941p01`'s panel is 36
hand-authored quads around a cylinder — 7.5 deg apart, and the part carries only
10 type-5 lines — so neither fired and the panel shattered into separately
stroked fragments. Decoration now unions across curvature.

**The `absorb_wall_facets` color guard was never implemented.** It remains a
genuine fourth color-blind merge, but no part is known to hit it. Add it only
with a part that demonstrates the bug; do not add it on this plan's say-so.

---

### Task 7: Gate — unprinted parts must not have moved

**Files:** none modified — this is the regression gate.

- [ ] **Step 1: Re-render and split the comparison**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg \
  --shading outline --shade-style flat3 --out debug/unwrap/after6
cd debug/unwrap
find after6 -name '*.svg' -exec shasum -a 256 {} + | sed 's|after6/||' | sort > after6.sha
grep -vE '(3941p01|3942bp01|3068bp00|3040bp08)\.svg' after6.sha > after6-18.sha
grep -vE '(3941p01|3942bp01|3068bp00|3040bp08)\.svg' before.sha > before-18.sha
diff before-18.sha after6-18.sha && echo "18 UNPRINTED BYTE-IDENTICAL"
cd ../..
```

Expected: `18 UNPRINTED BYTE-IDENTICAL`. Any difference means the merge guards changed undecorated geometry — STOP and find it. Every specimen but the four printed ones is single-colored, so no color boundary exists to split.

- [ ] **Step 2: Confirm the printed four DID change**

```bash
cd debug/unwrap
grep -E '(3941p01|3942bp01|3068bp00|3040bp08)\.svg' before.sha > before-4.sha
grep -E '(3941p01|3942bp01|3068bp00|3040bp08)\.svg' after6.sha > after6-4.sha
diff before-4.sha after6-4.sha > /dev/null && echo "UNCHANGED — BUG" || echo "all four moved, as intended"
cd ../..
```

Expected: `all four moved, as intended`. If unchanged, the painting never reached them.

- [ ] **Step 3: Commit the new baseline**

```bash
cd debug/unwrap && cp after6.sha baseline-v3.sha && cd ../..
git add specimens.txt 2>/dev/null; git commit --allow-empty \
  -m "re-baseline the specimen gate after decoration painting

debug/unwrap/baseline-v3.sha supersedes baseline-v2.sha. The 18 unprinted
specimens are byte-identical; the four printed ones changed by design."
```

---

### Task 8: Bind decoration regions to an analytic carrier

**Files:**
- Create: `brick_icons/unwrap.py`
- Test: `tests/test_unwrap.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_unwrap.py`:

```python
import numpy as np
import pytest

from brick_icons import geom2d, unwrap


class FakeCylinder:
    """Stand-in for primitives.Cylinder: unit circle in R's x/z, axis R[:,1]."""
    def __init__(self, r=20.0, h=24.0):
        self.R = np.diag([r, h, r]).astype(float)
        self.t = np.zeros(3)


def test_binds_a_facet_on_the_wall_to_its_cylinder():
    cyl = FakeCylinder(r=20.0)
    on_wall = np.array([[20.0, 1.0, 0.0], [19.6, 1.0, 4.0], [20.0, 5.0, 0.0]])
    assert unwrap.bind(on_wall, [cyl]) is cyl


def test_does_not_bind_geometry_further_than_the_tolerance():
    cyl = FakeCylinder(r=20.0)
    standoff = np.array([[24.0, 1.0, 0.0], [24.0, 1.0, 4.0], [24.0, 5.0, 0.0]])
    assert unwrap.bind(standoff, [cyl]) is None


def test_tolerance_is_half_an_ldu():
    """0.5 LDU binds every measured case (3040bp08 worst at 0.345) with an
    order of magnitude under the smallest real feature (a stud is 12 across)."""
    assert unwrap.BIND_TOL == 0.5


def test_unbound_geometry_is_left_as_authored():
    """An unrecognized construction must degrade to today's output, never
    raise — 4,764 printed parts, most never eyeballed."""
    weird = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    assert unwrap.bind(weird, []) is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.unwrap'`

- [ ] **Step 3: Write the module**

Create `brick_icons/unwrap.py`:

```python
"""Map a decal into its carrier's parameter space and back onto the exact
surface.

Every carrier goes through here — planar, cylinder and cone — because the
planar map being the identity is a degenerate case of the general one, not a
reason to skip it. One path means the flat case cannot drift; and unwrapping
first dissolves authored faceting (3941p01's panel is 36 quads approximating a
16-gon, which in (theta, h) is one rounded rectangle), so re-projection onto
the analytic carrier yields exact arcs instead of inheriting the author's
segment count.
"""
from __future__ import annotations

import numpy as np

BIND_TOL = 0.5          # LDU; see the plan's measured table


def _axis_frame(prim):
    """(origin, axis unit vector, radius) for a cylinder/cone-like primitive."""
    A = prim.R[:, 1]
    h = float(np.linalg.norm(A))
    return prim.t, A / h if h else A, float(np.linalg.norm(prim.R[:, 0]))


def _radial_gap(pts, prim) -> float:
    o, a, r = _axis_frame(prim)
    d = np.asarray(pts, float) - o
    perp = d - np.outer(d @ a, a)
    return float(np.max(np.abs(np.linalg.norm(perp, axis=1) - r)))


def _gap(pts, carrier) -> float:
    """Distance from `pts` to the carrier surface, by carrier kind. A planar
    carrier measures offset FROM the face; a radial metric would report
    position ALONG it, which is why 6141p01 and 3001p01 read 6.5 and 2.0 LDU
    under the axis measure — artifacts, not standoffs."""
    if isinstance(carrier, Plane):
        n = carrier.normal / np.linalg.norm(carrier.normal)
        return float(np.max(np.abs(np.asarray(pts, float) @ n - carrier.offset)))
    return _radial_gap(pts, carrier)


def bind(pts, carriers, tol: float = BIND_TOL):
    """The carrier `pts` lies on, or None. None means 'leave as authored'."""
    best, best_gap = None, tol
    for c in carriers:
        try:
            gap = _gap(pts, c)
        except (AttributeError, ValueError, IndexError):
            continue
        if gap <= best_gap:
            best, best_gap = c, gap
    return best
```

`Plane` is defined in Task 9; if you are executing strictly in order, write
`_gap` with only the `_radial_gap` branch now and add the `Plane` branch when
Task 9 introduces the class.

**Where carriers come from.** Cylinders and cones are already in
`out["analytic"]` from `hlr.flatten`. Planes are not primitives and must be
derived: collect the distinct `plane` keys (`shade.py:1595`) of the body
(`color == 16`) faces and build a `Plane` per key. Do that in Task 13's wiring
step, not here.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/unwrap.py tests/test_unwrap.py
git commit -m "bind decal facets to the analytic carrier they lie on"
```

---

### Task 9: The unwrap maps

**Files:**
- Modify: `brick_icons/unwrap.py`
- Test: `tests/test_unwrap.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unwrap.py`:

```python
def test_cylinder_unwrap_uses_arc_length_not_degrees():
    """Degrees against LDU is an arbitrary aspect; arc length makes the
    texture isometric with the surface, so a round lamp stays round."""
    cyl = FakeCylinder(r=20.0)
    quarter = np.array([[20.0, 0.0, 0.0], [0.0, 0.0, 20.0]])
    uv = unwrap.to_uv(quarter, cyl)
    assert uv[:, 1] == pytest.approx([0.0, 0.0])
    # a quarter turn at r=20 is 20 * pi/2 of arc
    assert uv[1, 0] - uv[0, 0] == pytest.approx(20.0 * np.pi / 2, rel=1e-6)


def test_cylinder_unwrap_round_trips():
    cyl = FakeCylinder(r=20.0)
    pts = np.array([[20.0, 3.0, 0.0], [0.0, 7.0, 20.0], [-20.0, 1.0, 0.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, cyl), cyl)
    assert back == pytest.approx(pts, abs=1e-9)


def test_faceted_ring_reprojects_onto_the_exact_radius():
    """The point of the whole exercise: chord midpoints authored at r=19.616
    (a 16-gon inscribed in r=20) come back at exactly 20."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, 2 * np.pi, 17)[:-1] + np.pi / 16
    chord = np.column_stack([19.616 * np.cos(th),
                             np.zeros(16), 19.616 * np.sin(th)])
    back = unwrap.to_xyz(unwrap.to_uv(chord, cyl), cyl)
    assert np.hypot(back[:, 0], back[:, 2]) == pytest.approx(20.0, abs=1e-9)


def test_planar_unwrap_is_the_identity_in_the_face_basis():
    plane = unwrap.Plane(normal=np.array([0.0, 1.0, 0.0]), offset=2.0)
    pts = np.array([[3.0, 2.0, 5.0], [-1.0, 2.0, 4.0]])
    back = unwrap.to_xyz(unwrap.to_uv(pts, plane), plane)
    assert back == pytest.approx(pts, abs=1e-9)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -k uv -q`
Expected: FAIL with `AttributeError: module 'brick_icons.unwrap' has no attribute 'to_uv'`

- [ ] **Step 3: Implement the maps**

Append to `brick_icons/unwrap.py`:

```python
from dataclasses import dataclass, field


@dataclass
class Plane:
    """A flat carrier. Its unwrap is the identity in the face's own basis."""
    normal: np.ndarray
    offset: float
    _basis: tuple = field(default=None, repr=False)

    def basis(self):
        if self._basis is None:
            n = self.normal / np.linalg.norm(self.normal)
            seed = np.array([0.0, 0.0, 1.0]) if abs(n[2]) < 0.9 \
                else np.array([1.0, 0.0, 0.0])
            u = np.cross(n, seed)
            u /= np.linalg.norm(u)
            self._basis = (n, u, np.cross(n, u))
        return self._basis


def to_uv(pts, carrier):
    """Carrier parameter space, in LDU on both axes so one uniform scale
    keeps the texture isometric."""
    pts = np.asarray(pts, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return np.column_stack([pts @ u, pts @ v])
    o, a, r = _axis_frame(carrier)
    d = pts - o
    height = d @ a
    perp = d - np.outer(height, a)
    e1 = carrier.R[:, 0] / np.linalg.norm(carrier.R[:, 0])
    e2 = np.cross(a, e1)
    return np.column_stack([r * np.arctan2(perp @ e2, perp @ e1), height])


def to_xyz(uv, carrier):
    """Back onto the EXACT surface — this is where the sagitta closes."""
    uv = np.asarray(uv, float)
    if isinstance(carrier, Plane):
        n, u, v = carrier.basis()
        return (np.outer(uv[:, 0], u) + np.outer(uv[:, 1], v)
                + carrier.offset * n)
    o, a, r = _axis_frame(carrier)
    e1 = carrier.R[:, 0] / np.linalg.norm(carrier.R[:, 0])
    e2 = np.cross(a, e1)
    th = uv[:, 0] / r
    return (o + np.outer(r * np.cos(th), e1) + np.outer(r * np.sin(th), e2)
            + np.outer(uv[:, 1], a))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/unwrap.py tests/test_unwrap.py
git commit -m "unwrap and re-project decals through carrier parameter space"
```

---

### Task 10: Emit the unwrap as a standalone texture

**Files:**
- Modify: `brick_icons/unwrap.py`, `brick_icons/cli.py`
- Test: `tests/test_unwrap.py` (append)

The spec asks for this as its own stage, and it earns the place twice: it is the only way to see whether a carrier bound correctly without reading projected output, and being 2-D and camera-independent it is far easier to assert on than a render.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unwrap.py`:

```python
def test_texture_canvas_comes_from_the_carrier_not_the_decal():
    """Scaling the decal's own bbox to a fixed canvas warps it — round lamps
    become ellipses. The carrier's extent and ONE scale factor fix that."""
    carrier_uv = np.array([[0.0, 0.0], [40.0, 0.0], [40.0, 20.0], [0.0, 20.0]])
    decal_uv = [np.array([[10.0, 8.0], [14.0, 8.0], [14.0, 12.0], [10.0, 12.0]])]
    svg = unwrap.texture_svg(carrier_uv, [(4, decal_uv[0])], px=400)
    assert 'width="400"' in svg and 'height="200"' in svg   # 40:20, not 1:1


def test_texture_paints_each_region_in_its_ldraw_color():
    carrier_uv = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    region = np.array([[2.0, 2.0], [8.0, 2.0], [8.0, 8.0], [2.0, 8.0]])
    svg = unwrap.texture_svg(carrier_uv, [(14, region)], px=100)
    assert "#fac80a" in svg.lower()      # LDraw 14, Yellow
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -k texture -q`
Expected: FAIL with `AttributeError: module 'brick_icons.unwrap' has no attribute 'texture_svg'`

- [ ] **Step 3: Implement it**

Append to `brick_icons/unwrap.py`:

```python
from . import colors as _colors


def texture_svg(carrier_uv, regions, px=900, ldraw_dir="vendor/ldraw"):
    """The decal laid flat, canvas set by the carrier at ONE uniform scale."""
    cu = np.asarray(carrier_uv, float)
    x0, y0 = cu.min(axis=0)
    x1, y1 = cu.max(axis=0)
    s = px / max(x1 - x0, y1 - y0, 1e-9)
    w, h = (x1 - x0) * s, (y1 - y0) * s
    body = []
    for code, poly in regions:
        hex_str, _ = _colors.resolve(str(code), ldraw_dir)
        pts = np.asarray(poly, float)
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{(p[0] - x0) * s:.2f},{(y1 - p[1]) * s:.2f}"
            for i, p in enumerate(pts))
        body.append(f'<path d="{d} Z" fill="#{hex_str[2:]}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}"><rect width="{w:.0f}" height="{h:.0f}" '
            f'fill="#ffffff"/>' + "".join(body) + "</svg>")
```

- [ ] **Step 4: Write it from the CLI**

In `brick_icons/cli.py`, find the existing debug stage emitter with
`grep -n "_stage" brick_icons/cli.py`, and write `<part>.unwrap.svg` into
`--debug-dir` alongside the per-stage PNGs, once per bound carrier.

- [ ] **Step 5: Run the tests and look at the artifact**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: 10 passed

```bash
.venv/bin/brick-icons 3941p01 --root . --format svg --shading outline \
  --shade-style flat3 --debug-dir debug/unwrap/stages --out debug/unwrap/t10
open debug/unwrap/stages/3941p01.unwrap.svg
```

Expected: two black rounded rectangles, each with 8 button holes — the panels laid flat, positioned on the cylinder's full angular extent.

- [ ] **Step 6: Commit**

```bash
git add brick_icons/unwrap.py brick_icons/cli.py tests/test_unwrap.py
git commit -m "emit the unwrapped decal as a standalone texture"
```

---

### Task 11: Merge same-color facets into one region in UV

**Files:**
- Modify: `brick_icons/unwrap.py`
- Test: `tests/test_unwrap.py` (append)

LDraw has no curves and no regions — the yellow arrow on `3068bp00` is 11
triangles, `3040bp08`'s border is 68 facets. Unioned in UV they become one
path each, and every interior facet edge disappears with the union. That is
what stops a print reading as a mesh.

**A border is a frame, so it needs a hole.** `3040bp08`'s border is not a
filled rectangle: it is an outer rounded rectangle minus an inner one, and its
68 facets must union into ONE path with ONE interior ring, not into a solid
slab or a ring of separate bars. Shapely's union produces that hole for free
when the facets genuinely enclose an empty middle; the work is carrying the
interior ring through to the emitted path data rather than keeping only the
exterior. The `test_a_hole_survives_the_merge` case below pins exactly this,
and `region_path` in Task 12 must emit the hole as a second subpath.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unwrap.py`:

```python
def test_two_facets_sharing_an_edge_merge_to_one_four_corner_region():
    a = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    b = np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0]])
    merged = unwrap.merge_regions([(4, a), (4, b)])
    assert len(merged) == 1
    code, g = merged[0]
    assert code == 4
    rings = geom2d.rings(g)
    assert len(rings) == 1
    assert len(rings[0]) == 4                  # the shared edge is gone


def test_different_colors_stay_separate_regions():
    a = np.array([[0.0, 0.0], [2.0, 0.0], [2.0, 2.0], [0.0, 2.0]])
    b = np.array([[2.0, 0.0], [4.0, 0.0], [4.0, 2.0], [2.0, 2.0]])
    assert len(unwrap.merge_regions([(4, a), (14, b)])) == 2


def test_a_hole_survives_the_merge():
    """3941p01's buttons are body-colored discs INSIDE the black panel: the
    panel region must keep them as holes, not swallow them."""
    outer = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]])
    merged = unwrap.merge_regions([(0, outer)],
                                  holes=[np.array([[4.0, 4.0], [6.0, 4.0],
                                                   [6.0, 6.0], [4.0, 6.0]])])
    assert len(merged) == 1
    assert unwrap.region_has_hole(merged[0][1])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -k merge -q`
Expected: FAIL with `AttributeError: module 'brick_icons.unwrap' has no attribute 'merge_regions'`

- [ ] **Step 3: Implement it on the existing geom2d primitives**

Append to `brick_icons/unwrap.py`:

```python
from . import geom2d


def merge_regions(regions, holes=None):
    """Union same-color facets in UV. Interior facet edges vanish with the
    union — a decal is one region, not a mesh."""
    by_code = {}
    for code, poly in regions:
        by_code.setdefault(code, []).append(
            geom2d.to_geom(np.asarray(poly, float)))
    cut = [geom2d.to_geom(np.asarray(h, float)) for h in (holes or [])]
    out = []
    for code, geoms in by_code.items():
        g = geom2d.union_all(geoms)
        for h in cut:
            g = geom2d.difference(g, h)
        out.append((code, g))
    return out


def region_has_hole(g) -> bool:
    return any(len(getattr(part, "interiors", ())) for part in
               (getattr(g, "geoms", None) or [g]))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/unwrap.py tests/test_unwrap.py
git commit -m "union same-color decal facets into one region in UV"
```

---

### Task 12: Recover circles in UV

**Files:**
- Modify: `brick_icons/unwrap.py`
- Test: `tests/test_unwrap.py` (append)

**Fit rounded rectangles first, then circles.** A rounded rectangle is the most
common decal shape by far — panels, borders, fields, plaques — and recognising
one collapses dozens of facets plus four corner fans into a single `rect` with
an `rx`, which is both exact and tiny. Test for it before the circle fit: four
axis-aligned straight runs joined by four equal-radius quarter arcs. `3941p01`'s
panel and `3040bp08`'s border are both this shape, and both currently emit as
many-vertex polygons with square corners.

**Subtract enclosed regions rather than tiling around them.** `3941p01`'s eight
buttons and `3040bp08`'s frame interior are holes in their region, not gaps
between neighbouring pieces. Unioning the facets and subtracting the enclosed
shape yields ONE path with interior rings; letting the enclosed shape split the
region instead produces the strips of separately-stroked fragments seen before
this task.

Fitting circles is markedly easier here than in projected space, and the reason
is worth stating: UV has no camera. The existing `arcfit` fights foreshortening
(a circle projects to an ellipse) and chord-proxy occlusion. In UV a decal
circle is a circle, so `arcfit._fit_circle` is an exact fit rather than a
best-effort one.

**The one caveat:** a flat disc lying against a *curved* wall unrolls to only
approximately a circle — exactly on a plane, near-exactly for a small feature
on a large radius (`3941p01`'s buttons are ~2 LDU on r=20), worse on a cone.
So fit, then check the residual, and keep the polygon when the fit is poor.
Never assume the fit succeeded.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unwrap.py`:

```python
def test_a_16gon_fan_is_recovered_as_a_circle():
    """3040bp08's lamps and 3941p01's buttons are 16-gon fans, not circles."""
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    poly = np.column_stack([3.0 + 2.0 * np.cos(th), 5.0 + 2.0 * np.sin(th)])
    fit = unwrap.fit_circle(poly)
    assert fit is not None
    cx, cy, r = fit
    assert (cx, cy) == pytest.approx((3.0, 5.0), abs=1e-6)
    assert r == pytest.approx(2.0, rel=1e-3)


def test_a_square_is_not_mistaken_for_a_circle():
    square = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]])
    assert unwrap.fit_circle(square) is None


def test_a_poor_fit_is_rejected_rather_than_forced():
    """An egg — a circle stretched 30% on one axis — must not pass."""
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    egg = np.column_stack([2.6 * np.cos(th), 2.0 * np.sin(th)])
    assert unwrap.fit_circle(egg) is None


def test_region_path_emits_arc_commands_for_a_recovered_circle():
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    poly = np.column_stack([3.0 + 2.0 * np.cos(th), 5.0 + 2.0 * np.sin(th)])
    d = unwrap.region_path(geom2d.to_geom(poly))
    assert "A" in d              # true arcs, not 16 L commands
    assert d.count("L") <= 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -k circle -q`
Expected: FAIL with `AttributeError: module 'brick_icons.unwrap' has no attribute 'fit_circle'`

- [ ] **Step 3: Implement fit and emission**

Append to `brick_icons/unwrap.py`:

```python
from . import arcfit

CIRCLE_TOL = 0.02       # LDU of radial residual; a 16-gon's own sagitta at
                        # r=2 is 0.038, so fit the VERTICES, not the chords


def fit_circle(poly, tol: float = CIRCLE_TOL):
    """(cx, cy, r) when `poly`'s vertices lie on a common circle, else None.
    Returning None is the normal outcome for a square and must stay cheap —
    most decal regions are not circles."""
    pts = np.asarray(poly, float)
    if len(pts) < 8:                     # too few to distinguish from a box
        return None
    fit = arcfit._fit_circle(pts)
    if fit is None:
        return None
    cx, cy, r = fit[0], fit[1], fit[2]
    resid = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - r)
    return (cx, cy, r) if float(resid.max()) <= tol else None


def region_path(g, tol=CIRCLE_TOL):
    """SVG path data for a UV region, with recovered circles as A commands."""
    cands = []
    for ring in geom2d.rings(g):
        fit = fit_circle(ring, tol)
        if fit is not None:
            cx, cy, r = fit
            cands.append({"cx": cx, "cy": cy, "rx": r, "ry": r, "rot": 0.0})
    return geom2d.path_d(g, arcs=geom2d.arc_candidates(cands) if cands else None)
```

Check `geom2d.arc_candidates`'s expected input shape first with
`sed -n '46,70p' brick_icons/geom2d.py` and match it — it takes projected
ellipses today, and a UV circle is the degenerate `rx == ry`, `rot == 0` case.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -q`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/unwrap.py tests/test_unwrap.py
git commit -m "recover decal circles as true arcs in UV"
```

---

### Task 13: Route decoration through the unwrap in the render path

**Files:**
- Modify: `brick_icons/shade.py`
- Test: `tests/test_unwrap.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_unwrap.py`:

```python
def test_reprojection_closes_the_sagitta_gap():
    """3941p01's panel is authored as a 16-gon inscribed in the r=20 wall, so
    its chord midpoints fall 0.384 LDU inside the cylinder and open a white
    seam. After the round trip every point is ON the wall."""
    cyl = FakeCylinder(r=20.0)
    th = np.linspace(0, 2 * np.pi, 17)[:-1]
    verts = np.column_stack([20.0 * np.cos(th), np.zeros(16),
                             20.0 * np.sin(th)])
    mids = (verts + np.roll(verts, -1, axis=0)) / 2
    assert np.hypot(mids[:, 0], mids[:, 2]).min() < 19.7          # the gap
    fixed = unwrap.to_xyz(unwrap.to_uv(mids, cyl), cyl)
    assert np.hypot(fixed[:, 0], fixed[:, 2]) == pytest.approx(20.0, abs=1e-9)


def test_geometry_binding_to_no_carrier_is_untouched():
    """4,764 printed parts, most never eyeballed: an unrecognized
    construction must degrade to today's output, not raise."""
    weird = np.array([[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]])
    assert unwrap.decorate(weird, [4], carriers=[]) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_unwrap.py -k "sagitta or untouched" -q`
Expected: FAIL with `AttributeError: module 'brick_icons.unwrap' has no attribute 'decorate'`

- [ ] **Step 3: Add the entry point**

Append to `brick_icons/unwrap.py`:

```python
def decorate(tris, tri_colors, carriers):
    """[(code, carrier, region_geom)] for every decoration group that binds.
    Triangles binding to no carrier are omitted, and their caller leaves the
    authored geometry alone."""
    groups = {}
    for tri, code in zip(np.asarray(tris, float), tri_colors):
        if code == 16:
            continue
        carrier = bind(tri, carriers)
        if carrier is None:
            continue
        groups.setdefault((id(carrier), code), (carrier, code, []))[2].append(
            to_uv(tri, carrier))
    out = []
    for carrier, code, polys in groups.values():
        for c, g in merge_regions([(code, p) for p in polys]):
            out.append((c, carrier, g))
    return out
```

- [ ] **Step 4: Wire it into `shade.faces_from_tris`'s caller**

In `brick_icons/shade.py`, before face dicts are built, call
`unwrap.decorate(tri, tri_colors, analytic_carriers)`. For each returned
region, replace its member triangles with geometry re-projected through
`unwrap.to_xyz`, and emit its boundary with `unwrap.region_path`. Triangles in
no returned group pass through exactly as today.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 391 passed

- [ ] **Step 6: Commit**

```bash
git add brick_icons/shade.py brick_icons/unwrap.py tests/test_unwrap.py
git commit -m "re-project unwrapped decals onto the exact carrier surface"
```

---

### Task 14: Final gates

**Files:**
- Test: `tests/test_unwrap.py` (append)

- [ ] **Step 1: The seam regression test the spec asks for**

Append to `tests/test_unwrap.py`:

```python
def test_decal_paints_its_ldraw_color_end_to_end(tmp_path):
    """The sagitta seam showed as a body-colored sliver along the panel's
    lower edge; the panel itself never painted at all."""
    from brick_icons import cli
    out = tmp_path / "o"
    cli.main(["3941p01", "--root", ".", "--format", "svg",
              "--shading", "outline", "--shade-style", "flat3",
              "--out", str(out)])
    svg = (out / "3941p01.svg").read_text().lower()
    assert "#05131d" in svg          # LDraw 0, Black — the panel
```

Confirm the expected hex first: `.venv/bin/brick-icons --list-colors | head -3`.

- [ ] **Step 2: Byte-diff gate**

```bash
.venv/bin/brick-icons --list specimens.txt --root . --format svg \
  --shading outline --shade-style flat3 --out debug/unwrap/final
cd debug/unwrap
find final -name '*.svg' -exec shasum -a 256 {} + | sed 's|final/||' | sort > final.sha
grep -vE '(3941p01|3942bp01|3068bp00|3040bp08)\.svg' final.sha > final-18.sha
diff before-18.sha final-18.sha && echo "18 UNPRINTED STILL BYTE-IDENTICAL"
cd ../..
```

Expected: `18 UNPRINTED STILL BYTE-IDENTICAL`. The unwrap must not touch
undecorated geometry.

- [ ] **Step 3: Compare all four against LDView**

```bash
.venv/bin/python scripts/render-references.py 3941p01 3942bp01 3068bp00 3040bp08 \
  --out out/final
open out/final/references.png
```

Expected, checked by eye against the top row: `3941p01` black panels with white
buttons; `3942bp01` 16 red stripes in 4 bands; `3068bp00` a yellow arrow;
`3040bp08` a yellow border, 3 yellow lamps, 3 red squares. Read it
structurally — LDView's faceting differs from ours by design, so never
pixel-diff.

- [ ] **Step 4: Confirm the meshes are gone**

```bash
grep -o 'A' debug/unwrap/final/3040bp08.svg | wc -l
```

Expected: non-zero — the lamps emit arc commands rather than 16-gon polylines.

- [ ] **Step 5: Full suite and commit**

Run: `.venv/bin/python -m pytest -q`
Expected: 392 passed

```bash
git add tests/test_unwrap.py
git commit -m "gate decal unwrap against LDView and the specimen baseline"
```

---

## Done when

- All four printed specimens render their print in the right colors, matching LDView structurally.
- The 18 unprinted specimens are byte-identical to `debug/unwrap/before.sha`.
- `debug/<part>.unwrap.svg` shows the decal laid flat on its carrier's extent.
- A decal authored as a faceted 16-gon re-projects onto the exact carrier radius, closing the sagitta seam.
- Geometry that binds to no carrier renders exactly as it does today.

## Deliberately not in this plan

- **The spec's limb-clipping guard.** It exists to catch a decal snapped
  outward from r=19.65 to r=20 crossing a silhouette. The measurement in the
  spec's own later paragraph retracts that reading — decal and carrier are
  co-radial to 0.074 LDU, there is no snap, so there is nothing to clip.
- **Spheres** (minifig heads such as `3626bp01`) — out of scope per the spec; they bind to no carrier and pass through unchanged.
- **`4740p03`'s `TopologyException`** — undiagnosed, and not caused by anything here.
- **Uncapped linear gradient stops** (`shade.py:1313`) — `3960p01` carries 640. Independent of decals.
- **The unwanted ink pockets** on `30137`, `98283`, `32062` — that inking closed the graze-shard and pinhole classes and needs its own gated task.
