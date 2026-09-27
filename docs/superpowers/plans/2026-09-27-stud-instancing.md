**Status: plan, not started (2026-09-27).**

# Stud Instancing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Behind `--stud-instancing off|all` (default `off`), classify every declared stud before the engine runs. A stud that is clear or cut only by planes stays in the engine as an occluder but stops adding edges and faces. It is drawn once per distinct stud through the same engine and placed at every position: `<use>` in the SVG, translated stroke ops in the PNGs.

**Architecture:** A new module `brick_icons/instancing.py` holds the classification, the withholding, the envelopes, the definition cache and the placement. `hlr.flatten` tags type-2/5 lines and triangles with their stud and records each stud reference. `hlr.visible_segments` runs `instancing.withhold` between flatten and `sweep.substitute`, then the rest of the pipeline through a factored-out `hlr.draw_flattened`, which a lone stud reuses. Engines skip withheld geometry: naive by tag; occt by tag, envelope and limb locus. `trace`/`process` gain a placement layer between part fills and part strokes. `cli.process_one` wires it, and translucent and wireframe renders force it off.

**Tech Stack:** Python 3.14, numpy, shapely 2.1, OCP (occt engine), PIL, pytest; fleet runs through `onto`.

---

## Where this plan differs from the spec (read first)

1. **Cut clip source.** A cut stud's clip is `footprint − cover`. The cover comes from the occluders the samples hit, projected before the engine runs. For a `DiscOccluder` it is the primitive's own disc or ring outline. For a `TriangleOccluder` it is the triangles sharing the hit plane that overlap the stud. The spec takes it from the engine's fitted face polygons, but classification has to finish first, so a fallback stud keeps its drawing role. Every clip is checked against the samples; any disagreement makes the stud a fallback.
2. **occt provenance.** The sewn shape carries no stud tag. occt withholds a sewn face, or an analytic crease circle, lying wholly inside a withheld stud's *envelope*: a cylinder about the stud's local Y axis sized by its own declared geometry. It drops HLR outline edges lying on a withheld stud wall's limb line.
3. **Contour hiding (not in the spec).** Once studs leave the silhouette, the part contour runs behind the back-row studs. It is clipped out under placed studs: `contour_hide` in the SVG, `cut_rings` for the PNGs.
4. **Definition key** also carries `body` and the inherited winding, `invert`. Both change how the lone stud draws.
5. **Other studs are occluders** during classification. Two studs overlapping each other are cut when the front one's top disc is what hides the other, and fall back when its wall is.

## File structure

| file | change | responsibility |
|---|---|---|
| `brick_icons/instancing.py` | **create** | `StudRef`/`Verdict`/`Plan`; `stud_points`, `classify`, `withhold`, `Envelopes`, `limb_points`, `grow_bbox`; `Instancer` (lone-stud definition cache, `svg_parts`, `png_ops`, `hide_region`); `origin_fit`, `translate_op`, `clip_ops`, `cut_rings`, `canvas_geom` |
| `brick_icons/hlr.py` | modify | `flatten` tags `2_stud`/`5_stud`/`tri_meta["stud"]` and records `stud_refs`; `VisResult.studs`; `affine_segments`; `kept_tris`; `draw_flattened` (split from `visible_segments`); `visible_segments(stud_instancing=)`; naive engine skips withheld prims and tris |
| `brick_icons/primitives.py` | modify | `Primitive.withheld`; `OccluderIndex.nearest_hit` |
| `brick_icons/sweep.py` | modify | frustums inherit `withheld` from the quads they replace |
| `brick_icons/occt.py` | modify | `authored_loci(held=)`, `_withheld_limb_loci`, `_off_loci`, `_held_face`, `ordered_faces(skip_face=)`, `_with_decoration` skips withheld |
| `brick_icons/trace.py` | modify | `fill_elements`, `stroke_elements` split out; `segments_to_svg(between=, contour_hide=)` |
| `brick_icons/process.py` | modify | `draw_segments`/`segments_mono(stud_ops=, stud_px=, contour_open=)` |
| `brick_icons/config.py` | modify | `stud_instancing` default `"off"` |
| `brick_icons/cli.py` | modify | `--stud-instancing`, `render_tag`, `process_one` wiring, `_png_contour` |
| `scripts/compare-silhouette-truth.py` | modify | `--stud-instancing` passthrough; named in `drawn_as` when on |
| `scripts/vet-goldens.py` | modify | `--after-args` |
| `scripts/stud-ab-timing.py` | **create** | interleaved off/all timing per part |
| `tests/test_instancing.py` | **create** | classification, withholding, envelope, keys, placement, integration |
| `tests/test_hlr.py`, `test_primitives.py`, `test_sweep.py`, `test_occt.py`, `test_trace.py`, `test_process.py`, `test_config.py`, `test_cli.py` | modify | tests per task |
| `tests/test_vet_goldens.py`, `tests/test_stud_ab_timing.py` | **create** | script tests |
| `docs/superpowers/specs/2026-09-27-stud-instancing-design.md`, `HANDOFF.md` | modify | status and handoff |

Coordinate spaces used throughout:

- **world** is LDU after flatten.
- **A/B** is `hlr.project(P, right, up, fwd)`: `A = P·right`, `B = −P·up`, depth `z = P·fwd`.
- **op space** is `res.proj.to_px(P)`. naive: render px. occt: `op_projection`, identity on A/B.
- **canvas** is `A·k + kx`, `B·k + ky` with `(k, kx, ky) = hlr.canvas_affine(res, *fit)` (`hlr.py:1467`).

A definition is drawn with `origin_fit` so its reference origin lands on canvas (0, 0). `<use x y>` is `(a·k + kx, b·k + ky)`, where `(a, b)` is the stud reference origin in A/B.

---

### Task 0: Baseline before any change

**Files:** none (outputs under `out/`, which is gitignored)

- [ ] **Step 1: Confirm the naive byte gate passes at HEAD**

Run: `BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py -q`
Expected: PASS. If it fails at HEAD, stop and report; the off-path proof in Task 15 depends on it.

- [ ] **Step 2: Record occt baselines for the off-path proof**

```bash
.venv/bin/python -m brick_icons.cli 3001 3941 --engine occt --format svg \
  --shading outline --shade-style flat3 --out out/stud-baseline
shasum -a 256 out/stud-baseline/*.svg > out/stud-baseline/SHA256
```
Expected: two SVGs plus `SHA256`. No commit.

---

### Task 1: Tag lines and triangles under a stud; record each stud reference

**Files:** Modify `brick_icons/hlr.py:160-193` (`flatten`); Test `tests/test_hlr.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_hlr.py`)

```python
def test_flatten_tags_every_line_and_triangle_under_a_stud(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "stud.dat").write_text(
        "0 Stud\n"
        "2 24 6 0 0 6 -4 0\n"
        "5 24 6 0 0 6 -4 0 5 0 1 5 0 -1\n"
        "3 16 0 -4 0 6 -4 0 0 -4 6\n"
        "1 16 0 -4 0 6 0 0 0 1 0 0 0 6 4-4disc.dat\n")
    part = tmp_path / "thing.dat"
    part.write_text(
        "2 24 0 0 0 10 0 0\n"
        "3 16 0 0 0 10 0 0 0 0 10\n"
        "1 16 5 0 5 1 0 0 0 1 0 0 0 1 p\\stud.dat\n")
    roots = hlr.default_roots(tmp_path)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    hlr.flatten(part, np.eye(3), np.zeros(3), out, roots)
    assert out["2_stud"] == [None, 1]
    assert out["5_stud"] == [1]
    assert [m["stud"] for m in out["tri_meta"]] == [None, 1]
    assert [p.stud for p in out["analytic"]] == [1]
    ref = out["stud_refs"][1]
    assert ref["path"].name == "stud.dat"
    assert np.allclose(ref["t"], [5, 0, 5]) and np.allclose(ref["R"], np.eye(3))
    assert ref["color"] == 16 and ref["body"] == 16 and ref["invert"] is False
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_hlr.py::test_flatten_tags_every_line_and_triangle_under_a_stud -q`
Expected: FAIL with `KeyError: '2_stud'`.

- [ ] **Step 3: Implement** — in `hlr.flatten`, replace the stud branch (currently `hlr.py:162-166`):

```python
                        if stud is None and is_stud(sub):
                            out["studs"] = out.get("studs", 0) + 1
                            sub_stud = out["studs"]
                            # what instancing needs to draw this stud again
                            # on its own: its file and the placement flatten
                            # hands it, winding included
                            out.setdefault("stud_refs", {})[sub_stud] = {
                                "path": sub, "R": Rsub, "t": tsub,
                                "color": cur,
                                "body": body if own_body is None else own_body,
                                "invert": bool(base_invert ^ invert_next
                                               ^ m_reflect)}
                        else:
                            sub_stud = stud
```

Replace the type-2/5 branch (`hlr.py:173-175`):

```python
        elif typ in ("2", "5") and len(tok) >= 8:
            pts = np.array(list(map(float, tok[2:])), float).reshape(-1, 3)
            out[typ].append(pts @ R.T + t)
            # the stud each line came from, parallel to out[typ] only until
            # something rewrites that list (sweep.substitute, arcfit):
            # visible_segments consumes and drops it before either runs
            out.setdefault(typ + "_stud", []).append(stud)
```

and add the tag to the triangle meta (`hlr.py:181-182`):

```python
                meta = {"certified": certified, "invert": tri_invert,
                        "color": cur, "body": body, "stud": stud}
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/test_hlr.py::test_flatten_tags_every_line_and_triangle_under_a_stud tests/test_hlr.py::test_studs_are_what_the_part_declared -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "tag the lines and triangles under a declared stud, and record each stud reference, in flatten" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `Primitive.withheld` and `OccluderIndex.nearest_hit`

**Files:** Modify `brick_icons/primitives.py:564` and `:1507`; Test `tests/test_primitives.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_primitives.py`)

```python
def test_occluder_index_names_the_nearest_occluder_each_ray_hits():
    F = np.array([0.0, 1.0, 0.0])
    near = P.DiscOccluder(np.diag([5.0, 1.0, 5.0]), np.array([0.0, 2.0, 0.0]),
                          360.0, 0.0, 1.0)
    far = P.DiscOccluder(np.diag([30.0, 1.0, 30.0]), np.array([0.0, 5.0, 0.0]),
                         360.0, 0.0, 1.0)
    index = P.OccluderIndex([near, far], F)
    O = np.array([[0.0, 0.0, 0.0], [20.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
    depth, which = index.nearest_hit(O)
    assert which.tolist() == [0, 1, -1]
    assert depth[:2].tolist() == [2.0, 5.0] and np.isinf(depth[2])
    depth, which = index.nearest_hit(O, skip=[near])
    assert which.tolist() == [1, 1, -1]


def test_a_primitive_is_not_withheld_until_instancing_says_so():
    prim = P.Disc(R=np.eye(3), t=np.zeros(3))
    assert prim.withheld is False
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_primitives.py::test_occluder_index_names_the_nearest_occluder_each_ray_hits tests/test_primitives.py::test_a_primitive_is_not_withheld_until_instancing_says_so -q`
Expected: FAIL with `AttributeError` (`nearest_hit`, `withheld`).

- [ ] **Step 3: Implement.** In `Primitive` after `stud = None ...` (`primitives.py:564-565`):

```python
    withheld = False         # set per instance by instancing.withhold: a
                             # stud instancing draws, so the engine must not
                             # (it still occludes)
```

In `OccluderIndex`, after `nearest`:

```python
    def nearest_hit(self, O, skip=()):
        """(depth, index) of the nearest occluder along F per ray: `index`
        into `self.occluders`, -1 on a miss. `skip` is a collection of
        occluders never tested -- a stud's own surfaces, when the question
        is what ELSE hides it (instancing.classify)."""
        O = np.atleast_2d(O).astype(float)
        field = np.full(O.shape[0], np.inf)
        which = np.full(O.shape[0], -1, dtype=int)
        if not self.occluders or not O.shape[0]:
            return field, which
        skip_ids = {id(o) for o in skip}
        for i in boxes_reached(self.lo, self.hi, O @ self.u, O @ self.v):
            occ = self.occluders[i]
            if id(occ) in skip_ids:
                continue
            d = occ.depth(O, self.F)
            closer = d < field
            field = np.where(closer, d, field)
            which = np.where(closer, int(i), which)
        return field, which
```

- [ ] **Step 4: Run them** — same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/primitives.py tests/test_primitives.py
git commit -m "add Primitive.withheld and OccluderIndex.nearest_hit, which names the occluder a ray hits" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Split `hlr` for reuse: `affine_segments`, `kept_tris`, `draw_flattened`, `VisResult.studs`

**Files:** Modify `brick_icons/hlr.py:21-24, 408-465, 467-587, 1169-1237, 1483-1496`; Test `tests/test_hlr.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_hlr.py`; add `from brick_icons import sweep` to its imports)

```python
def test_affine_segments_maps_lines_and_arcs_and_fit_segments_uses_it():
    ops = [("line", 1.0, 2.0, 3.0, 4.0, "edge"),
           ("arc", 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 90.0, "sil")]
    assert hlr.affine_segments(ops, 2.0, 10.0, 20.0) == [
        ("line", 12.0, 24.0, 16.0, 28.0, "edge"),
        ("arc", 10.0, 20.0, 2.0, 0.0, 0.0, 2.0, 0.0, 90.0, "sil")]
    bbox = (0.0, 0.0, 4.0, 4.0)
    assert hlr.fit_segments(ops, bbox, 100, 80) == hlr.affine_segments(
        ops, *hlr.fit_affine(bbox, 100, 80))


def test_vis_result_carries_no_stud_plan_by_default():
    assert hlr.VisResult([], (0, 0, 1, 1), 1.0, [], []).studs is None


def test_kept_tris_passes_out_s_own_lists_through_when_nothing_is_withheld():
    tris = [np.zeros((3, 3)), np.ones((3, 3))]
    out = {"tri": tris, "tri_colors": [16, 4],
           "tri_meta": [{"stud": None}, {"stud": 1}]}
    got, colors = hlr.kept_tris(out)
    assert got is tris and colors is out["tri_colors"]
    out["tri_meta"][1]["withheld"] = True
    got, colors = hlr.kept_tris(out)
    assert len(got) == 1 and got[0] is tris[0] and colors == [16]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_draw_flattened_is_visible_segments_after_the_flatten():
    roots = hlr.default_roots(LIB)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": [],
           "printed": False}
    hlr.flatten(hlr._resolve_input("3005", roots), np.eye(3), np.zeros(3),
                out, roots)
    for key in ("2_stud", "5_stud"):
        out.pop(key, None)
    sweep.substitute(out)
    right, up, fwd = hlr.view_basis(30.0, 45.0)
    got = hlr.draw_flattened(out, right, up, fwd, 600, engine="naive")
    want = hlr.visible_segments("3005", LIB, render_px=600, engine="naive")
    assert got.segs == want.segs and got.bbox == want.bbox
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -q -k "affine_segments or carries_no_stud_plan or kept_tris or draw_flattened"`
Expected: FAIL (`AttributeError` on `affine_segments`, `studs`, `kept_tris`, `draw_flattened`).

- [ ] **Step 3: Implement.**

(a) `VisResult` (`hlr.py:21-24`):

```python
# studs: the instancing.Plan when the render was drawn with stud instancing,
# else None.
VisResult = namedtuple("VisResult",
                       "segs bbox s faces analytic ellipses proj refits "
                       "fold_ells loops tri tri_colors sil_polys studs",
                       defaults=[(), None, (), (), (), (), (), (), None])
```

(b) Add `kept_tris` after `_is_printed` (`hlr.py:1166`):

```python
def kept_tris(out):
    """(triangles, colors) an engine may draw faces from: all of out's, less
    those under a stud instancing places (tri_meta "withheld", set by
    instancing.withhold). Out's own lists when none is withheld, so a render
    without instancing passes through untouched. `colors` is None where out
    carries none."""
    tris = out.get("tri") or []
    colors = out.get("tri_colors")
    meta = out.get("tri_meta") or []
    if not any(m.get("withheld") for m in meta):
        return tris, colors
    keep = [i for i, m in enumerate(meta) if not m.get("withheld")]
    return ([tris[i] for i in keep],
            None if colors is None else [colors[i] for i in keep])
```

(c) Replace `fit_segments` (`hlr.py:1483-1496`):

```python
def affine_segments(segs, f, ox, oy):
    """Ops mapped through a uniform scale `f` and offset (ox, oy) -- the fit
    fit_affine computes, or any other (instancing.origin_fit)."""
    out = []
    for op in segs:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        if op[0] == "line":
            _, x1, y1, x2, y2, k = op
            out.append(("line", x1 * f + ox, y1 * f + oy, x2 * f + ox, y2 * f + oy, k))
        else:
            _, cx, cy, ux, uy, vx, vy, t0, t1, k = op
            out.append(("arc", cx * f + ox, cy * f + oy,
                        ux * f, uy * f, vx * f, vy * f, t0, t1, k))
    return out


def fit_segments(segs, bbox, W, H, margin=6, scale=1.0):
    return affine_segments(segs, *fit_affine(bbox, W, H, margin, scale))
```

(d) Replace `visible_segments` (`hlr.py:1169-1237`) with the two functions below. Move the existing comments verbatim into `draw_flattened`: repair, arcfit, the occt import and dedupe notes.

```python
@timing.timed("geometry")
def visible_segments(part: str, ldraw_dir, lat=30.0, long=45.0, render_px=900,
                     cull=True, engine="naive", pose=None, canvas_px=None,
                     stud_instancing="off"):
    """`stud_instancing="all"` classifies every declared stud before the
    engine runs and withholds the drawing of each one instancing will place
    (instancing.withhold); the result carries that plan as `studs`. Only the
    naive and occt engines honor the withholding, so only they take it."""
    if engine not in VALID_ENGINES:
        raise ValueError(
            f"unrecognized engine {engine!r}; must be one of {VALID_ENGINES}")
    if stud_instancing not in ("off", "all"):
        raise ValueError(f"stud_instancing must be 'off' or 'all', "
                         f"not {stud_instancing!r}")
    roots = default_roots(ldraw_dir)
    path = _resolve_input(part, roots)
    out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": []}
    # (keep the existing comment block about decoration here)
    out["printed"] = _is_printed(path)
    right, up, fwd = view_basis(lat, long)
    plan = None
    with timing.phase("flatten"):
        # (keep the existing comment about the turn going in as the root basis)
        root = np.eye(3) if pose is None else np.asarray(pose, float)
        flatten(path, root, np.zeros(3), out, roots)
        if stud_instancing == "all" and engine in ("naive", "occt"):
            from . import instancing
            with timing.phase("studs"):
                plan = instancing.withhold(out, right, up, fwd)
        # the per-line stud tags are parallel to out["2"]/out["5"] only until
        # the passes below rewrite those lists; nothing after here reads them
        for key in ("2_stud", "5_stud"):
            out.pop(key, None)
        sweep.substitute(out)
    res = draw_flattened(out, right, up, fwd, render_px, cull=cull,
                         engine=engine, canvas_px=canvas_px)
    if plan is not None:
        res = res._replace(studs=plan, bbox=instancing.grow_bbox(
            res.bbox, plan, res.proj))
    return res


def draw_flattened(out, right, up, fwd, render_px=900, cull=True,
                   engine="naive", canvas_px=None):
    """Everything visible_segments does after the flatten -- repair, arcfit,
    the engine and the stylization tail -- on a flattened part that
    sweep.substitute has already run over. Split out so a stud drawn on its
    own (instancing.Instancer) takes exactly the part's path."""
    if out["tri"]:
        with timing.phase("repair"):
            fixed = repair.repaired_tris(np.array(out["tri"]),
                                         out["tri_meta"], MESH_CACHE_DIR)
        out["tri"] = list(fixed)
        out["tri_colors"] = [m["color"] for m in out["tri_meta"]]
    with timing.phase("arcfit"):
        out["fit_arcs"], out["2"] = arcfit.fit_edge_arcs(out["2"], out["5"])
    if engine == "occt":
        with timing.phase("import"):
            from . import occt
        res = occt.visible_segments(out, right, up, render_px, cull=cull,
                                    fwd=fwd, canvas_px=canvas_px)
        px = 1.0 / (res.s or 1.0)
        with timing.phase("dedupe"):
            segs = dedupe_segments(res.segs, eps=0.05 * px, keep_order=True)
        return _stylize(res, segs, cull, px)
    if engine == "cadquery":
        from . import cqsvg
        return cqsvg.visible_segments(out, right, up, render_px, cull=cull)
    if out["analytic"] or out["fit_arcs"]:
        with timing.phase("engine"):
            res = _visible_segments_analytic(out, right, up, fwd, render_px,
                                             cull=cull)
    else:
        with timing.phase("engine"):
            res = _visible_segments_faceted(out, right, up, fwd, render_px,
                                            cull=cull)
    with timing.phase("dedupe"):
        segs = dedupe_segments(res.segs)
    res = _stylize(res, segs, cull, px=1.0)
    return res._replace(tri=out["tri"], tri_colors=out.get("tri_colors", ()))
```

(`instancing` is imported only inside the `if`, and `plan is not None` only on that path, so the name is always bound where it is used.)

- [ ] **Step 4: Run them**

Run: `.venv/bin/python -m pytest tests/test_hlr.py -q -k "affine_segments or carries_no_stud_plan or kept_tris or draw_flattened or studs_are" && BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py -q`
Expected: PASS (the golden gate proves the split moved no byte).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_hlr.py
git commit -m "split draw_flattened out of visible_segments, and add affine_segments, kept_tris and VisResult.studs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Classify each stud (`instancing.py`, part 1)

**Files:** Create `brick_icons/instancing.py`; Create `tests/test_instancing.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_instancing.py`:

```python
"""Stud instancing: classification, withholding, and the placed drawing."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from shapely.geometry import Point, box

from brick_icons import cli, hlr, instancing, primitives, timing

LIB = Path("vendor/ldraw")
HAVE_LIB = LIB.exists()
RIGHT, UP, FWD = hlr.view_basis(30.0, 45.0)


def _stud_out():
    """One stud as flatten leaves it: stud.dat's wall and top at the origin,
    tagged stud 1, with its reference recorded."""
    wall = primitives.Cylinder(R=np.diag([6.0, -4.0, 6.0]), t=np.zeros(3))
    top = primitives.Disc(R=np.diag([6.0, 1.0, 6.0]),
                          t=np.array([0.0, -4.0, 0.0]))
    for p in (wall, top):
        p.stud = 1
    return {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": [wall, top],
            "2_stud": [], "5_stud": [],
            "stud_refs": {1: {"path": Path("p/stud.dat"), "R": np.eye(3),
                              "t": np.zeros(3), "color": 16, "body": 16,
                              "invert": False}}}


def _ground(out, tris):
    """Add non-stud triangles to `out`."""
    for v in tris:
        out["tri"].append(np.asarray(v, float))
        out["tri_meta"].append({"certified": True, "invert": False,
                                "color": 16, "body": 16, "stud": None})
    return out


def _screen_quad(a0, a1, b0, b1, depth):
    """Two triangles square to the view at camera depth `depth`, spanning
    projected A in [a0, a1] and B in [b0, b1]."""
    def at(a, b):
        return depth * FWD + a * RIGHT - b * UP
    q = [at(a0, b0), at(a1, b0), at(a1, b1), at(a0, b1)]
    return [np.array([q[0], q[1], q[2]]), np.array([q[0], q[2], q[3]])]


def _bar():
    """A fat cylinder standing in front of the stud's right half."""
    return primitives.Cylinder(R=np.column_stack([8 * RIGHT, 40 * UP, 8 * FWD]),
                               t=-30 * FWD + 6 * RIGHT - 20 * UP)


def test_a_stud_nothing_hides_is_clear():
    [v] = instancing.classify(_stud_out(), RIGHT, UP, FWD)
    assert v.role == "clear" and v.ref.id == 1


def test_a_plane_behind_a_stud_does_not_hide_it():
    out = _ground(_stud_out(), _screen_quad(-30, 30, -30, 30, 20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "clear"


def test_a_stud_behind_a_plane_is_hidden():
    out = _ground(_stud_out(), _screen_quad(-30, 30, -30, 30, -20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "hidden"


def test_a_stud_half_behind_a_plane_is_cut_by_its_outline():
    out = _ground(_stud_out(), _screen_quad(0, 30, -30, 30, -20.0))
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "cut"
    a, b, _ = hlr.project(np.array([[0.0, -4.0, 0.0]]), RIGHT, UP, FWD)
    shown = v.shown()
    assert shown.contains(Point(a[0] - 3, b[0]))
    assert not shown.contains(Point(a[0] + 3, b[0]))


def test_a_stud_half_behind_a_cylinder_falls_back_to_the_engine():
    out = _stud_out()
    out["analytic"].append(_bar())
    [v] = instancing.classify(out, RIGHT, UP, FWD)
    assert v.role == "fallback"


def test_a_definition_is_keyed_on_file_basis_color_and_winding_not_position():
    def ref(t, R=np.eye(3), color=16, invert=False, path="p/stud.dat"):
        return instancing.StudRef(1, Path(path), np.asarray(R, float),
                                  np.asarray(t, float), color, 16, invert)
    base = ref([0, 0, 0])
    assert ref([20, 0, 40]).key == base.key
    assert ref([0, 0, 0], R=np.eye(3) + 1e-7).key == base.key
    assert ref([0, 0, 0], color=4).key != base.key
    assert ref([0, 0, 0], invert=True).key != base.key
    assert ref([0, 0, 0], path="p/stud2.dat").key != base.key
    assert ref([0, 0, 0], R=np.diag([1.0, 1.0, -1.0])).key != base.key


def test_studs_are_placed_far_to_near():
    ref = instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                             16, 16, False)
    near = instancing.Verdict(ref, "clear", hull=box(0, 0, 1, 1), depth=1.0)
    far = instancing.Verdict(ref, "cut", hull=box(0, 0, 1, 1),
                             cover=box(0, 0, 0.5, 1), depth=5.0)
    gone = instancing.Verdict(ref, "hidden", depth=9.0)
    plan = instancing.Plan([near, far, gone], (RIGHT, UP, FWD))
    assert plan.placed() == [far, near]
    assert plan.counts() == {"clear": 1, "cut": 1, "hidden": 1, "fallback": 0}
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_instancing.py -q`
Expected: FAIL with `ImportError: cannot import name 'instancing'`.

- [ ] **Step 3: Implement** — create `brick_icons/instancing.py`:

```python
"""Stud instancing: draw each declared stud once, and place it wherever it
shows.

A stud is what the part DECLARED as one -- geometry under a `p/stud*.dat`
reference that `hlr.is_stud` accepts, tagged by `hlr.flatten` -- and under an
orthographic view every stud of one file, basis and color is the same drawing
moved. So before the engine runs each stud is tested against everything that
is not itself (`classify`): nothing in front of it, it is `clear`; everything,
`hidden`; only planes, `cut` by their outline; anything curved, or anything
the outline cannot account for, `fallback`, and the engine draws it as it
always did. Every stud that is not a fallback stays in the engine's input as
an occluder and stops contributing edges and faces (`withhold`). `Instancer`
draws each distinct stud once, alone, through the same engine at the part's
scale, and both writers place that one drawing.

Spec: docs/superpowers/specs/2026-09-27-stud-instancing-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import MultiPoint, Polygon

from . import hlr, primitives

#: Angles sampled round each circle of a stud when classifying it.
SAMPLES = 24
#: Heights sampled on a stud's wall: both rims and half way up.
WALL_LEVELS = (0.0, 0.5, 1.0)
#: How far (projected LDU) a sample may sit on the wrong side of a cut
#: stud's cover outline and still agree with it: a sample ON the outline is
#: hit or missed by float noise.
AGREE_LDU = 0.05
#: Depth tolerance as a fraction of the part's depth range -- the naive
#: engine's own (hlr._visible_segments_analytic): a stud's base rim lies ON
#: the plate it stands on.
DEPTH_EPS = 1e-3
#: How far (LDU) a hit may sit off a triangle's plane and still lie on it.
PLANE_TOL = 1e-3
ROLES = ("clear", "cut", "hidden", "fallback")
PLACED = ("clear", "cut")


@dataclass(frozen=True, eq=False)
class StudRef:
    """One stud reference as flatten placed it (hlr.flatten's stud_refs)."""
    id: int
    path: Path
    R: np.ndarray
    t: np.ndarray
    color: int
    body: int
    invert: bool

    @property
    def key(self):
        """What makes two studs the same drawing moved: the file, the basis
        (rounded, so authoring noise does not split a baseplate's studs), the
        color and body (decoration), and the winding (back-face culling)."""
        return (Path(self.path).name.lower(),
                tuple(float(x) for x in np.round(self.R, 4).ravel()),
                int(self.color), int(self.body), bool(self.invert))


@dataclass(eq=False)
class Verdict:
    """One stud's classification. `hull` is everything it covers and `cover`
    (cut only) the planes in front of it, both world A/B; (a, b, depth) is
    its reference origin projected."""
    ref: StudRef
    role: str
    hull: object = None
    cover: object = None
    a: float = 0.0
    b: float = 0.0
    depth: float = 0.0

    def shown(self):
        """What of the stud the drawing shows, world A/B."""
        if self.hull is None:
            return None
        if self.role == "cut":
            from . import geom2d
            return geom2d.difference(self.hull, self.cover)
        return self.hull


@dataclass(eq=False)
class Plan:
    """Every stud's verdict for one render, and the view it was made in."""
    verdicts: list
    basis: tuple
    printed: bool = False

    def counts(self):
        c = {r: 0 for r in ROLES}
        for v in self.verdicts:
            c[v.role] += 1
        return c

    def placed(self):
        """The studs instancing draws -- clear and cut -- far to near, so a
        nearer stud paints over a farther one."""
        return sorted((v for v in self.verdicts if v.role in PLACED),
                      key=lambda v: -v.depth)


def refs_of(out):
    return [StudRef(id=i, path=Path(r["path"]), R=np.asarray(r["R"], float),
                    t=np.asarray(r["t"], float), color=int(r["color"]),
                    body=int(r["body"]), invert=bool(r["invert"]))
            for i, r in sorted(out.get("stud_refs", {}).items())]


def members(out):
    """({stud id: [prims]}, {stud id: [tris]}) of what flatten tagged."""
    prims, tris = {}, {}
    for p in out.get("analytic", ()):
        if p.stud is not None:
            prims.setdefault(p.stud, []).append(p)
    for v, m in zip(out.get("tri", ()), out.get("tri_meta", ())):
        if m.get("stud") is not None:
            tris.setdefault(m["stud"], []).append(np.asarray(v, float))
    return prims, tris


def stud_points(prims, tris, n=SAMPLES):
    """World points on a stud's declared geometry: each primitive's circles
    over its own sector (a wall's rims and middle, a ring's bore, a disc's
    half-radius ring and center, a partial sector's center) and each
    triangle's corners and centroid."""
    pts = []
    for p in prims:
        th = np.radians(np.linspace(0.0, p.sector, n))
        for lv in (WALL_LEVELS if p.kind in ("cyli", "con") else (0.0,)):
            pts.append(p.ring_pts(th, lv))
        if p.kind == "ring":
            pts.append(p.ring_pts(th, 0.0, radius=float(p.inner)))
        if p.kind == "disc":
            pts.append(p.ring_pts(th, 0.0, radius=0.5))
            pts.append(p.t[None, :])
        elif not p.is_full:
            pts.append(p.t[None, :])
    for v in tris:
        v = np.asarray(v, float)
        pts.append(v)
        pts.append(v.mean(axis=0)[None, :])
    return np.vstack(pts) if pts else np.zeros((0, 3))


def _depth_range(out, fwd):
    pts = ([np.asarray(out["tri"], float).reshape(-1, 3)]
           if out.get("tri") else [])
    pts += [p.fit_pts() for p in out.get("analytic", ())]
    if not pts:
        return 1.0
    z = np.vstack(pts) @ np.asarray(fwd, float)
    return float(z.max() - z.min()) or 1.0


def _ab(P, right, up, fwd):
    a, b, _ = hlr.project(np.asarray(P, float), right, up, fwd)
    return np.stack([a, b], 1)


def prim_region(prim, right, up, fwd, n=64):
    """A flat primitive's projected outline, world A/B: a disc, or a ring
    with its bore."""
    th = np.radians(np.linspace(0.0, prim.sector, n))
    outer = prim.ring_pts(th, 0.0)
    inner = (prim.ring_pts(th, 0.0, radius=float(prim.inner))
             if prim.kind == "ring" else None)
    holes = []
    if prim.is_full:
        shell = outer
        if inner is not None:
            holes = [inner]
    elif inner is not None:
        shell = np.vstack([outer, inner[::-1]])
    else:
        shell = np.vstack([outer, prim.t[None, :]])
    return Polygon(_ab(shell, right, up, fwd),
                   [_ab(h, right, up, fwd) for h in holes]).buffer(0)


def _plane_keys(T):
    """(unit normals, offsets, keys) per triangle, one sign per plane
    whichever way a triangle winds; a degenerate one's key is None."""
    e0, e1 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]
    n = np.cross(e0, e1)
    ln = np.linalg.norm(n, axis=1)
    ok = ln > 1e-12
    n[ok] /= ln[ok, None]
    lead = np.take_along_axis(
        n, np.argmax(np.abs(n) > 1e-6, axis=1)[:, None], 1)[:, 0]
    n *= np.where(lead < 0, -1.0, 1.0)[:, None]
    d = np.einsum("ij,ij->i", n, T[:, 0])
    keys = [(tuple(float(x) for x in np.round(n[i], 4)), round(float(d[i]), 2))
            if ok[i] else None for i in range(len(T))]
    return n, d, keys


def _in_tri2(q, x, y, slack=1e-6):
    (x0, y0), (x1, y1), (x2, y2) = q
    den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(den) < 1e-12:
        return False
    l0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / den
    l1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / den
    return l0 >= -slack and l1 >= -slack and 1.0 - l0 - l1 >= -slack


def _tri_cover(tris, hits, hull, right, up, fwd):
    """The projected outline (world A/B) of the planes the `hits` landed on:
    every triangle lying in one of those planes and reaching the stud's
    hull."""
    T = np.asarray(tris, float)
    n, d, keys = _plane_keys(T)
    q = _ab(T.reshape(-1, 3), right, up, fwd).reshape(-1, 3, 2)
    h2 = _ab(hits, right, up, fwd)
    planes = set()
    for H, (x, y) in zip(hits, h2):
        for i in np.nonzero(np.abs(n @ H - d) < PLANE_TOL)[0]:
            if keys[i] is not None and _in_tri2(q[i], x, y):
                planes.add(keys[i])
    if not planes:
        return Polygon()
    x0, y0, x1, y1 = hull.bounds
    lo, hi = q.min(axis=1), q.max(axis=1)
    near = ((hi[:, 0] >= x0) & (lo[:, 0] <= x1)
            & (hi[:, 1] >= y0) & (lo[:, 1] <= y1))
    polys = [Polygon(q[i]) for i in np.nonzero(near)[0] if keys[i] in planes]
    polys = [g for g in polys if g.area > 0]
    return shapely.union_all(polys) if polys else Polygon()


def _judge(hidden, which, depth, O, fwd, a, b, index, prim_of, hull,
           right, up):
    if not hidden.any():
        return "clear", None
    if hidden.all():
        return "hidden", None
    regions = []
    for i in sorted({int(w) for w in which[hidden]}):
        occ = index.occluders[i]
        if isinstance(occ, primitives.DiscOccluder) and id(occ) in prim_of:
            regions.append(prim_region(prim_of[id(occ)], right, up, fwd))
        elif isinstance(occ, primitives.TriangleOccluder):
            m = hidden & (which == i)
            hits = O[m] + depth[m][:, None] * fwd[None, :]
            regions.append(_tri_cover(occ.tris, hits, hull, right, up, fwd))
        else:
            return "fallback", None     # curved, or nothing here can outline it
    cover = shapely.union_all(regions)
    pts = shapely.points(a, b)
    grown, shrunk = cover.buffer(AGREE_LDU), cover.buffer(-AGREE_LDU)
    if ((hidden & ~shapely.covers(grown, pts)).any()
            or (~hidden & shapely.covers(shrunk, pts)).any()):
        return "fallback", None         # the outline does not explain the hits
    return "cut", cover


def classify(out, right, up, fwd):
    """A Verdict per stud flatten recorded, from sampling its geometry
    against every occluder that is not its own. Reads `out` as flatten left
    it (stud tags intact) and changes nothing."""
    refs = refs_of(out)
    if not refs:
        return []
    fwd = np.asarray(fwd, float)
    prims, tris = members(out)
    occluders, prim_of = [], {}
    for p in out.get("analytic", ()):
        occ = p.occluder()
        if occ is not None:
            occluders.append(occ)
            prim_of[id(occ)] = p
    ground = [np.asarray(v, float)
              for v, m in zip(out.get("tri", ()), out.get("tri_meta", ()))
              if m.get("stud") is None]
    if ground:
        occluders.append(primitives.TriangleOccluder(np.array(ground)))
    own_tris = {}
    for sid, ts in tris.items():
        own_tris[sid] = primitives.TriangleOccluder(np.array(ts))
        occluders.append(own_tris[sid])
    index = primitives.OccluderIndex(occluders, fwd)
    eps = DEPTH_EPS * _depth_range(out, fwd)
    verdicts = []
    for ref in refs:
        a0, b0, z0 = hlr.project(ref.t[None, :], right, up, fwd)
        at = dict(a=float(a0[0]), b=float(b0[0]), depth=float(z0[0]))
        ps, ts = prims.get(ref.id, []), tris.get(ref.id, [])
        P = stud_points(ps, ts)
        if not len(P):
            verdicts.append(Verdict(ref, "fallback", **at))
            continue
        a, b, z = hlr.project(P, right, up, fwd)
        hull = MultiPoint(np.stack([a, b], 1)).convex_hull
        own = [p.occluder() for p in ps if p.occluder() is not None]
        if ref.id in own_tris:
            own.append(own_tris[ref.id])
        O = P - z[:, None] * fwd[None, :]
        depth, which = index.nearest_hit(O, skip=own)
        hidden = z > depth + eps
        role, cover = _judge(hidden, which, depth, O, fwd, a, b, index,
                             prim_of, hull, right, up)
        verdicts.append(Verdict(ref, role, hull=hull, cover=cover, **at))
    return verdicts
```

- [ ] **Step 4: Run them** — `.venv/bin/python -m pytest tests/test_instancing.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/instancing.py tests/test_instancing.py
git commit -m "classify each declared stud as clear, cut, hidden or fallback against everything but itself" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Withhold placed studs; envelopes, limbs, bbox; sweep carries `withheld`

**Files:** Modify `brick_icons/instancing.py`, `brick_icons/sweep.py:419-423`; Test `tests/test_instancing.py`, `tests/test_sweep.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_instancing.py`:

```python
def test_withhold_takes_placed_studs_out_of_the_drawing_and_counts_them():
    out = _stud_out()
    keep_edge, stud_edge = np.zeros((2, 3)), np.ones((2, 3))
    out["2"], out["2_stud"] = [keep_edge, stud_edge], [None, 1]
    timing.reset()
    plan = instancing.withhold(out, RIGHT, UP, FWD)
    assert [v.role for v in plan.verdicts] == ["clear"]
    assert all(p.withheld for p in out["analytic"])
    assert len(out["2"]) == 1 and out["2"][0] is keep_edge
    assert out["stud_held"].holds(np.array([[0.0, -4.0, 0.0], [6.0, -4.0, 0.0]]))
    assert timing.counts() == {"studs_clear": 1, "studs_cut": 0,
                               "studs_hidden": 0, "studs_fallback": 0}


def test_withhold_leaves_a_fallback_stud_to_the_engine():
    out = _stud_out()
    out["analytic"].append(_bar())
    plan = instancing.withhold(out, RIGHT, UP, FWD)
    assert plan.counts()["fallback"] == 1
    assert not any(p.withheld for p in out["analytic"])
    assert "stud_held" not in out


def test_an_envelope_holds_only_what_lies_inside_its_stud():
    out = _stud_out()
    ref = instancing.refs_of(out)[0]
    env = instancing.Envelopes([(ref, instancing.stud_points(out["analytic"], []))])
    assert env.holds(np.array([[0.0, -2.0, 0.0], [0.0, -4.0, 6.0]]))
    assert not env.holds(np.array([[0.0, 3.0, 0.0]]))           # under the base
    assert not env.holds(np.array([[0.0, -2.0, 0.0], [20.0, -2.0, 0.0]]))


def test_a_wall_s_limbs_run_base_to_top_square_to_the_view():
    wall = _stud_out()["analytic"][0]
    limbs = instancing.limb_points(wall, FWD)
    assert len(limbs) == 2
    for base, top in limbs:
        assert abs((base - wall.t) @ FWD) < 1e-9
        assert np.allclose(top - base, wall.R[:, 1])


def test_the_bbox_grows_over_every_placed_stud():
    ref = instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                             16, 16, False)
    plan = instancing.Plan([instancing.Verdict(ref, "clear",
                                               hull=box(-6, -6, 6, 6))],
                           (RIGHT, UP, FWD))
    ident = primitives.Projection(RIGHT, UP, FWD, s=1.0, cx=0.0, cy=0.0, half=0.0)
    assert instancing.grow_bbox((0.0, 0.0, 1.0, 1.0), plan, ident) == (-6.0, -6.0, 6.0, 6.0)
    px = primitives.Projection(RIGHT, UP, FWD, s=2.0, cx=1.0, cy=1.0, half=100.0)
    assert instancing.grow_bbox((90.0, 90.0, 95.0, 95.0), plan, px) == (86.0, 86.0, 110.0, 110.0)
```

Append to `tests/test_sweep.py`:

```python
def test_a_tube_under_a_withheld_stud_stays_withheld_as_frustums(tmp_path):
    rings = []
    for k in range(9):
        t = math.radians(90 * k / 8)
        c = np.array([40 * math.cos(t), 40 * math.sin(t), 0.0])
        tangent = np.array([-math.sin(t), math.cos(t), 0.0])
        rings.append(_ring(c, 4.0, tangent, 16))
    p = tmp_path / "tube.dat"
    _write(p, rings)
    out = _flatten(p)
    for m in out["tri_meta"]:
        m["withheld"] = True
    assert sweep.substitute(out) == 1
    frustums = [q for q in out["analytic"] if getattr(q, "sweep", False)]
    assert frustums and all(q.withheld for q in frustums)
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_instancing.py tests/test_sweep.py::test_a_tube_under_a_withheld_stud_stays_withheld_as_frustums -q`
Expected: FAIL (`AttributeError: module 'brick_icons.instancing' has no attribute 'withhold'`; the sweep test fails its `withheld` assertion).

- [ ] **Step 3: Implement.** Append to `brick_icons/instancing.py` (add `import math` and `from . import timing` to its imports):

```python
#: Slack, in the stud's local units, of the envelope `Envelopes` tests.
ENVELOPE_TOL = 0.02


class Envelopes:
    """The space each withheld stud occupies: a cylinder about the stud's
    own local Y axis, as wide and as tall as its declared geometry. The sewn
    shape occt draws from carries no stud tag, so occt asks here whether a
    face or crease lies wholly inside one."""

    def __init__(self, items):
        self._env, lo, hi = [], [], []
        for ref, P in items:
            P = np.asarray(P, float)
            if not len(P):
                continue
            Minv = np.linalg.inv(ref.R)
            L = (P - ref.t) @ Minv.T
            self._env.append((Minv, ref.t,
                              float(np.hypot(L[:, 0], L[:, 2]).max()),
                              float(L[:, 1].min()), float(L[:, 1].max())))
            # the samples are inscribed in the true circles: pad the box
            pad = 0.05 * float((P.max(0) - P.min(0)).max()) + ENVELOPE_TOL
            lo.append(P.min(0) - pad)
            hi.append(P.max(0) + pad)
        self._lo = np.array(lo, float).reshape(-1, 3)
        self._hi = np.array(hi, float).reshape(-1, 3)

    def __len__(self):
        return len(self._env)

    def holds(self, P):
        P = np.atleast_2d(np.asarray(P, float))
        if not len(P) or not self._env:
            return False
        pmin, pmax = P.min(0), P.max(0)
        for i in np.nonzero(np.all(self._lo <= pmin, 1)
                            & np.all(self._hi >= pmax, 1))[0]:
            Minv, t, r, y0, y1 = self._env[i]
            L = (P - t) @ Minv.T
            if (np.hypot(L[:, 0], L[:, 2]).max() <= r + ENVELOPE_TOL
                    and L[:, 1].min() >= y0 - ENVELOPE_TOL
                    and L[:, 1].max() <= y1 + ENVELOPE_TOL):
                return True
        return False


def withhold(out, right, up, fwd):
    """Classify every stud and take each one instancing will place (every
    role but fallback) out of the drawing: its primitives and triangles are
    marked `withheld` -- still occluders, never drawn -- and its type-2 and
    type-5 lines leave out["2"] and out["5"]. Runs on `out` as flatten left
    it, before sweep.substitute and arcfit rewrite those lists. Records the
    four role counts for the census."""
    verdicts = classify(out, right, up, fwd)
    gone = {v.ref.id for v in verdicts if v.role != "fallback"}
    if gone:
        for p in out.get("analytic", ()):
            if p.stud in gone:
                p.withheld = True
        for m in out.get("tri_meta", ()):
            if m.get("stud") in gone:
                m["withheld"] = True
        for typ in ("2", "5"):
            lines = out.get(typ, [])
            tags = out.get(typ + "_stud") or [None] * len(lines)
            out[typ] = [e for e, s in zip(lines, tags) if s not in gone]
            out[typ + "_stud"] = [s for s in tags if s not in gone]
        prims, tris = members(out)
        out["stud_held"] = Envelopes(
            [(v.ref, stud_points(prims.get(v.ref.id, []),
                                 tris.get(v.ref.id, [])))
             for v in verdicts if v.ref.id in gone])
    plan = Plan(verdicts, (right, up, fwd), printed=bool(out.get("printed")))
    for role, n in plan.counts().items():
        timing.count(f"studs_{role}", n)
    return plan


def limb_points(prim, fwd):
    """World (base, top) of each limb generator of a cylinder or cone
    primitive seen along `fwd` -- the lines Cylinder/Cone.drawn_with_depth
    draw as its silhouette. [] for other kinds, or a cone with no limb."""
    fwd = np.asarray(fwd, float)
    g = np.linalg.inv(prim.R) @ fwd
    if prim.kind == "cyli":
        th0 = math.atan2(-float(g[0]), float(g[2]))
        thetas, rb, rt = (th0, th0 + math.pi), 1.0, 1.0
    elif prim.kind == "con":
        a_, b_, c_ = float(g[0]), float(g[2]), float(-g[1])
        hyp = math.hypot(a_, b_)
        if hyp < 1e-12 or abs(c_) > hyp:
            return []
        phi0 = math.atan2(b_, a_)
        d = math.acos(max(-1.0, min(1.0, c_ / hyp)))
        thetas, rb, rt = (phi0 + d, phi0 - d), prim.top + 1.0, float(prim.top)
    else:
        return []
    out = []
    for th in thetas:
        if not prim.is_full and math.degrees(th) % 360.0 > prim.sector + 1e-6:
            continue
        base = prim.ring_pts(np.array([th]), 0.0, radius=rb)[0]
        top = prim.ring_pts(np.array([th]), 1.0, radius=rt)[0]
        out.append((base, top))
    return out


def grow_bbox(bbox, plan, proj):
    """`bbox` (op space) grown over what every placed stud shows: a withheld
    stud draws no op, and a naive bbox is its ops'."""
    if proj is None:
        return bbox
    x0, y0, x1, y1 = bbox
    for v in plan.placed():
        g = v.shown()
        if g is None or g.is_empty:
            continue
        a0, b0, a1, b1 = g.bounds
        x0 = min(x0, (a0 - proj.cx) * proj.s + proj.half)
        y0 = min(y0, (b0 - proj.cy) * proj.s + proj.half)
        x1 = max(x1, (a1 - proj.cx) * proj.s + proj.half)
        y1 = max(y1, (b1 - proj.cy) * proj.s + proj.half)
    return (float(x0), float(y0), float(x1), float(y1))
```

In `brick_icons/sweep.py`, inside `substitute`, right after `prim.bend = _bend(...) if BENDS else None`:

```python
                # a tube authored under a stud instancing places is that
                # stud's, and stays out of the drawing with it
                prim.withheld = bool(meta.get("withheld", False))
```

- [ ] **Step 4: Run them** — same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/instancing.py brick_icons/sweep.py tests/test_instancing.py tests/test_sweep.py
git commit -m "withhold every stud instancing places from the drawing, keeping it as an occluder" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The naive engine honors `withheld`

**Files:** Modify `brick_icons/hlr.py` (`_visible_segments_faceted` ~458-461, `_visible_segments_analytic` ~508-513 and ~571-574); Test `tests/test_instancing.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_instancing.py`)

```python
@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_every_stud_of_a_2x4_brick_is_clear_and_leaves_the_naive_drawing():
    timing.reset()
    off = hlr.visible_segments("3001", LIB, render_px=600, engine="naive")
    on = hlr.visible_segments("3001", LIB, render_px=600, engine="naive",
                              stud_instancing="all")
    assert off.studs is None
    assert on.studs.counts() == {"clear": 8, "cut": 0, "hidden": 0, "fallback": 0}
    assert {k: v for k, v in timing.counts().items() if k.startswith("studs_")} \
        == {"studs_clear": 8, "studs_cut": 0, "studs_hidden": 0, "studs_fallback": 0}
    assert len(off.segs) - len(on.segs) >= 16
    assert len(off.faces) - len(on.faces) >= 16
    assert not any(f.get("prim") is not None and f["prim"].stud is not None
                   for f in on.faces)
    assert on.bbox[1] <= off.bbox[1] + 1.0          # the studs stay in frame
    with pytest.raises(ValueError):
        hlr.visible_segments("3001", LIB, engine="naive", stud_instancing="some")
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_instancing.py::test_every_stud_of_a_2x4_brick_is_clear_and_leaves_the_naive_drawing -q`
Expected: FAIL on the `segs`/`faces` difference: the studs are classified but still drawn.

- [ ] **Step 3: Implement** in `hlr.py`.

In `_visible_segments_analytic`, the drawn-op loop:

```python
    for prim in analytic:
        if id(prim) in ink or prim.withheld:
            continue                    # print, or a stud instancing draws
```

and the face build:

```python
    tris, tri_colors = kept_tris(out)
    tri_faces = shade.faces_from_tris(np.array(tris), proj,
                                      cond_edges=out["5"],
                                      colors=tri_colors) if tris else []
    an_faces = shade.faces_from_analytic(
        [p for p in analytic if not p.withheld], proj)
```

In `_visible_segments_faceted`, the face build:

```python
    kept, kept_colors = kept_tris(out)
    faces = shade.faces_from_tris(np.array(kept), proj, cond_edges=out["5"],
                                  colors=kept_colors) if len(kept) else []
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/test_instancing.py -q && BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/hlr.py tests/test_instancing.py
git commit -m "draw no edge or face of a withheld stud in the naive engine" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The occt engine honors `withheld`

**Files:** Modify `brick_icons/occt.py` (`authored_loci` ~1454, `visible_segments` ~3439-3552, `ordered_faces` ~3161, `_with_decoration` ~3241-3247); Test `tests/test_occt.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_occt.py`)

```python
def test_instanced_studs_leave_the_occt_drawing_but_not_the_shape(ldraw_dir):
    off = hlr.visible_segments("3001", ldraw_dir, render_px=512, engine="occt")
    on = hlr.visible_segments("3001", ldraw_dir, render_px=512, engine="occt",
                              stud_instancing="all")
    assert on.studs.counts()["clear"] == 8
    assert len(off.faces) - len(on.faces) >= 16      # top disc + wall spans
    assert len(off.segs) - len(on.segs) >= 16        # rims and limbs
    # the part's own top edges are still drawn, still hidden behind the studs
    assert len(on.segs) > 0
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_occt.py::test_instanced_studs_leave_the_occt_drawing_but_not_the_shape -q`
Expected: FAIL on the faces/segs difference.

- [ ] **Step 3: Implement** in `occt.py`.

`authored_loci` gets `held=None`:

```python
def authored_loci(shape, out, right, up, held=None):
    """... (existing docstring) ...

    `held` (instancing.Envelopes) holds every stud instancing places: its
    primitives are skipped by their `withheld` tag, and an analytic crease
    lying wholly inside one -- a stud's top meeting its wall -- is skipped
    by where it is, because the sewn shape carries no tag."""
```

In its analytic loop, before the kind test:

```python
    for prim in out["analytic"]:
        if prim.withheld:
            continue
        if prim.kind != "edge" and not prim.rims_declared:
            continue
```

In its crease loop, after `v = ...` and before building `loc`:

```python
        if held is not None:
            th = np.linspace(0.0, 2 * math.pi, 8, endpoint=False)
            ring = o + g.Radius() * (np.cos(th)[:, None] * u
                                     + np.sin(th)[:, None] * v)
            if held.holds(ring):
                continue
```

Add after `select_authored`:

```python
def _withheld_limb_loci(out, right, up, fwd):
    """Seg loci, in HLR's 2-D frame, of every withheld stud wall's limbs:
    HLR's outline compound draws them and cannot say whose they are."""
    from . import instancing
    ax, ay = _screen_axes(right, up)
    return [_seg_locus(a, b, "sil", ax, ay)
            for prim in out.get("analytic", ()) if prim.withheld
            for a, b in instancing.limb_points(prim, fwd)]


def _off_loci(edges, loci):
    """The edges lying on none of `loci`, in order (select_authored's test,
    inverted)."""
    if not loci:
        return list(edges)
    lb = _locus_bboxes(loci)
    kept = []
    for e in edges:
        try:
            pts = _fragment_points(e)
        except Exception:
            kept.append(e)
            continue
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        near = np.nonzero((lo[0] >= lb[:, 0]) & (hi[0] <= lb[:, 2])
                          & (lo[1] >= lb[:, 1]) & (hi[1] <= lb[:, 3]))[0]
        if not any(_on_locus(pts, loci[k]) for k in near):
            kept.append(e)
    return kept


def _held_face(held):
    """A predicate for ordered_faces: does this sewn face lie wholly inside
    a withheld stud? None when no stud is withheld."""
    if held is None:
        return None

    def skip(face):
        try:
            W = _wire_points(BRepTools.OuterWire_s(face))
        except Exception:
            return False
        return len(W) > 0 and held.holds(W)
    return skip
```

`ordered_faces` gets `skip_face=None`:

```python
def ordered_faces(shape, proj, out=None, ellipses_out=None, px=None,
                  skip_face=None):
    ...
    for face in _shape_faces(shape):
        if skip_face is not None and skip_face(face):
            continue                     # a stud instancing draws
        occ = _face_occluder(face)
```

In `visible_segments`, after the `fwd` default:

```python
    # a stud instancing places stays in the shape, to hide what is behind
    # it, and out of the drawing (instancing.withhold)
    held = out.get("stud_held") or None
```

then `loci = authored_loci(shape, out, right, up, held=held)`, and replace the outline loop:

```python
    limbs = _withheld_limb_loci(out, right, up, fwd)
    for name in ("outline", "outline_hidden"):
        comp = comps.get(name)
        if comp is None:
            continue
        for edge in _off_loci(_edges_of(comp), limbs):
            ops += _edge_ops(edge, "sil")
```

and the faces call:

```python
    faces = ordered_faces(shape, proj, out, ellipses_out=decal_ells,
                          px=canvas_px / span if canvas_px else s,
                          skip_face=_held_face(held))
```

In `_with_decoration` replace the two decoration sources:

```python
    tris, colors = hlr.kept_tris(out)
    if tris and colors:
        deco += [f for f in shade.faces_from_tris(
                     np.array(tris), proj, cond_edges=out.get("5"),
                     colors=colors)
                 if f.get("color", 16) != 16]
    prims = [p for p in out.get("analytic", ())
             if getattr(p, "color", 16) != 16 and not p.withheld]
```

- [ ] **Step 4: Run it**

Run: `.venv/bin/python -m pytest tests/test_occt.py::test_instanced_studs_leave_the_occt_drawing_but_not_the_shape tests/test_occt.py::test_3001_builds_and_sews -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/occt.py tests/test_occt.py
git commit -m "draw no edge, limb, crease or face of a withheld stud in the occt engine" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `trace` places a layer between fills and strokes, and hides contour under it

**Files:** Modify `brick_icons/trace.py:433-589`; Test `tests/test_trace.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_trace.py`)

```python
def test_between_paints_over_the_fills_and_under_the_strokes(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge")]
    fills = [{"d": "M 0 0 L 10 0 L 0 10 Z", "fill": "#cccccc", "depth": 1.0}]
    txt = _trace.segments_to_svg(segs, 20, 20, tmp_path / "b.svg", fills=fills,
                                 between=['<g class="studs"/>']).read_text()
    assert (txt.index('fill="#cccccc"') < txt.index('<g class="studs"/>')
            < txt.index('<g stroke="black"'))


def test_a_second_drawing_names_its_own_gradients():
    fills = [{"d": "M 0 0 L 10 0 L 10 10 Z", "depth": 1.0,
              "gradient": {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0,
                           "stops": [(0.0, "#333333"), (1.0, "#cccccc")]}}]
    defs, body = _trace.fill_elements(fills, gid_prefix="sd0g")
    assert 'id="sd0g0"' in defs[0] and "url(#sd0g0)" in body[1]
    assert body[0] == '<g stroke-linejoin="round">' and body[-1] == "</g>"


def test_stroke_elements_are_the_strokes_segments_to_svg_writes(tmp_path):
    segs = [("line", 0.0, 0.0, 10.0, 0.0, "edge"),
            ("arc", 5.0, 5.0, 3.0, 0.0, 0.0, 3.0, 0.0, 180.0, "edge")]
    txt = _trace.segments_to_svg(segs, 20, 20, tmp_path / "s.svg").read_text()
    for el in _trace.stroke_elements(segs, 2, 2):
        assert el in txt


def test_contour_hide_clips_the_contour_only(tmp_path):
    from shapely.geometry import box
    txt = _trace.segments_to_svg(
        [("line", 0.0, 0.0, 10.0, 0.0, "edge")], 20, 20, tmp_path / "c.svg",
        contour_d="M 1 1 L 19 1 L 19 19 Z",
        contour_hide=box(4, 0, 8, 3)).read_text()
    assert '<clipPath id="cclip">' in txt
    assert 'clip-path="url(#cclip)" stroke-width' in txt
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_trace.py -q -k "between or own_gradients or stroke_elements or contour_hide"`
Expected: FAIL (`TypeError: unexpected keyword 'between'`, `AttributeError: fill_elements`).

- [ ] **Step 3: Implement.** Three moves in `trace.py`; the bytes `segments_to_svg` writes do not change when `between` and `contour_hide` are None.

Add, above `segments_to_svg`, the body of today's `if fills:` block (`trace.py:454-509`) as its own function. The only change inside is the gradient id, `f"g{i}"` becoming `f"{gid_prefix}{i}"` in both branches:

```python
def fill_elements(fills, opacity=1.0, gid_prefix="g"):
    """(defs, body) for fill ops: the gradients they paint with, and the
    self-stroked paths inside one round-joined group. `gid_prefix` names the
    gradients; a second drawing in the same file (a stud definition, see
    instancing.Instancer) takes its own so the ids cannot collide."""
    # Each fill is stroked in its own paint (~0.8px) so antialiasing seams
    # between abutting coplanar faces don't show; gradient fills (cylinder
    # walls) carry a <linearGradient> def instead of a flat color.
    # Opacity is per-face: translucent renders skip occlusion clipping,
    # so faces overlap and each must blend individually (nearer over
    # deeper). The `opacity` attribute composites a path's own fill +
    # seam stroke together first, so a face never double-paints itself.
    face_op = f' opacity="{opacity:g}"' if opacity < 1.0 else ""
    defs, body = [], ['<g stroke-linejoin="round">']
    # Smooth-group facets share one gradient object; dedupe defs by
    # content so a 50-facet curve emits one <linearGradient>, not 50.
    def_ids = {}
    for i, fo in enumerate(fills):
        if "gradient" in fo:
            g = fo["gradient"]
            stops = "".join(
                f'<stop offset="{o * 100:.1f}%" stop-color="{c}"/>' for o, c in g["stops"])
            if g.get("type") == "radial":
                # unit-circle gradient space mapped onto the group's
                # bounding ellipse; fx/fy shift the bright spot lightward
                tf = (f'matrix({g["r"]:.2f} 0 0 {g["r"] * g["ratio"]:.2f} '
                      f'{g["cx"]:.2f} {g["cy"]:.2f})')
                key = ("radial", tf, f'{g["fx"]:.3f},{g["fy"]:.3f}', stops)
                gid = def_ids.get(key)
                if gid is None:
                    gid = f"{gid_prefix}{i}"
                    def_ids[key] = gid
                    defs.append(
                        f'<radialGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                        f'cx="0" cy="0" r="1" fx="{g["fx"]:.3f}" fy="{g["fy"]:.3f}" '
                        f'gradientTransform="{tf}">{stops}</radialGradient>')
            else:
                key = (f'{g["x1"]:.2f},{g["y1"]:.2f},{g["x2"]:.2f},{g["y2"]:.2f}', stops)
                gid = def_ids.get(key)
                if gid is None:
                    gid = f"{gid_prefix}{i}"
                    def_ids[key] = gid
                    defs.append(
                        f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" '
                        f'x1="{g["x1"]:.2f}" y1="{g["y1"]:.2f}" '
                        f'x2="{g["x2"]:.2f}" y2="{g["y2"]:.2f}">{stops}</linearGradient>')
            paint = f"url(#{gid})"
        else:
            paint = fo["fill"]
        # translucent fills paint fill-only: the self-stroke that closes
        # AA seams between abutting opaque fills double-paints its 0.4px
        # overhang onto neighbors when composited at opacity < 1 —
        # concentric ghost rings on a dish's stacked bands (4740)
        seam = (f' stroke="{paint}" stroke-width="0.8"'
                if opacity >= 1.0 else "")
        # class="deco" marks paint that is not the part's own color, so a
        # viewer can recolor the part without touching its printing
        deco = ' class="deco"' if fo.get("deco") else ""
        body.append(f'<path d="{fo["d"]}"{deco} fill="{paint}" '
                    f'fill-rule="evenodd"{seam}{face_op}/>')
    body.append("</g>")
    return defs, body
```

Below it, the stroke loop (`trace.py:536-571`, from `line_groups = {}` through the elbows loop), writing into a local list:

```python
def stroke_elements(segs, line_px, sil_px, studs=None):
    """SVG elements for stroke ops at their widths (process.stroke_width):
    arcs as paths, straight strokes chained into mitered polylines with
    elbow joins. The caller wraps them in the stroke group."""
    parts = []
    line_groups = {}                                  # sw -> [(x1,y1,x2,y2)]
    segs = _drop_sliver_loops(segs, 0.6 * line_px, 4.0 * line_px)
    for op in segs:
        if len(op) == 5:                              # legacy line tuple
            op = ("line",) + tuple(op)
        sw = process.stroke_width(op, line_px, sil_px, studs)
        if op[0] == "line":
            _, x1, y1, x2, y2, kind = op
            line_groups.setdefault(round(sw, 2), []).append(
                (round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)))
        else:
            r = (math.hypot(op[3], op[4]) + math.hypot(op[5], op[6])) / 2.0
            if r * math.radians(abs(op[8] - op[7])) < 0.6 * sw:
                continue
            parts.append(f'<path d="{_arc_to_svg(op)}" stroke-width="{sw:.2f}"/>')
    # straight strokes sharing endpoints chain into mitered polylines, with
    # elbow-join paths over the leftover corner wedges — separate
    # round-capped strokes pinch every 3D corner (see _chain_line_ops).
    # miterlimit 1.5 bevels joins sharper than ~84°: a longer miter tip is a
    # barb poking past the fill at interior corners (98283 ledge, 32062 notch
    # chevrons); outline corners stay sharp via contour_d, which keeps 5
    joinery = ' stroke-linejoin="miter" stroke-miterlimit="1.5"'
    for sw in sorted(line_groups):
        ops = _drop_sliver_noise(line_groups[sw], 0.6 * sw)
        chains, elbows, singles = _chain_line_ops(ops, stub_len=1.5 * sw)
        for pts, closed in chains:
            d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in pts) \
                + (" Z" if closed else "")
            parts.append(f'<path d="{d}" stroke-width="{sw:.2f}"{joinery}/>')
        for i in singles:
            x1, y1, x2, y2 = ops[i]
            parts.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
                         f'stroke-width="{sw:.2f}"/>')
        for (ax, ay), (vx, vy), (bx, by) in elbows:
            parts.append(f'<path d="M {ax:.2f} {ay:.2f} L {vx:.2f} {vy:.2f} '
                         f'L {bx:.2f} {by:.2f}" stroke-width="{sw:.2f}"{joinery}/>')
    return parts
```

`segments_to_svg` gains two keywords after `studs=None`: `between=None, contour_hide=None`. Its body from `parts = [root]` down to the `if debug_colors:` line becomes (the `physical` header above and everything from `if debug_colors:` on stay as they are):

```python
    parts = [root]
    if bg != "none":
        parts.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    if fills:
        defs, body = fill_elements(fills, opacity)
        if defs:
            parts.append("<defs>" + "".join(defs) + "</defs>")
        parts += body
    if between:
        # placed drawings (instancing's studs): over the part's fills,
        # under its strokes
        parts += between
    # Clip the stroke layer to the silhouette buffered outward by half the
    # widest stroke (mitered): round end caps otherwise poke half a width
    # past outline corners into the background ("frayed" corners).
    clip_attr = ""
    if clip_geom is not None:
        from . import geom2d
        # grow by drawn-arc bulge regions so the clip never flattens an arc
        clip = geom2d.union_all([clip_geom]
                                + geom2d.arc_regions(segs, clip_geom))
        cd = geom2d.buffer_d(clip, max(line_px, sil_px) / 2.0)
        if cd:
            parts.append(f'<defs><clipPath id="sclip">'
                         f'<path d="{cd}" clip-rule="evenodd"/></clipPath></defs>')
            clip_attr = ' clip-path="url(#sclip)"'
    contour_attr = ""
    if contour_d and contour_hide is not None and not contour_hide.is_empty:
        # the contour is the outline of the part's faces, not an engine
        # edge, so nothing hid it where a placed stud stands in front of it
        from . import geom2d
        from shapely.geometry import box
        keep = geom2d.path_d(geom2d.difference(box(-1, -1, w + 1, h + 1),
                                               contour_hide))
        if keep:
            parts.append(f'<defs><clipPath id="cclip"><path d="{keep}" '
                         f'clip-rule="evenodd"/></clipPath></defs>')
            contour_attr = ' clip-path="url(#cclip)"'
    stroke_g = len(parts)
    parts.append(f'<g stroke="black" fill="none" stroke-linecap="round"{clip_attr}>')
    if contour_d:
        # closed silhouette contour under the per-edge strokes: a closed path
        # has JOINS everywhere and no caps, so mitering it renders outline
        # corners sharp — the per-edge strokes' round vertex caps alone leave
        # them blunted
        parts.append(f'<path d="{contour_d}"{contour_attr} stroke-width="{sil_px:.2f}" '
                     f'stroke-linejoin="miter" stroke-miterlimit="5"/>')
    parts += stroke_elements(segs, line_px, sil_px, studs)
```

`arc_regions` still sees the unfiltered `segs`, as today: the sliver-loop drop moved into `stroke_elements` with the loop it fed. When `contour_hide` is None, `contour_attr` is `""`, so the contour element is byte-identical to today's.

- [ ] **Step 4: Run them**

Run: `.venv/bin/python -m pytest tests/test_trace.py -q && BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/trace.py tests/test_trace.py
git commit -m "split fill and stroke emission out of segments_to_svg, and take a placed layer and a contour hide region" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: `process` draws placed stud ops and an open contour

**Files:** Modify `brick_icons/process.py:130-169`; Test `tests/test_process.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_process.py`)

```python
def test_stud_ops_draw_at_their_own_width_after_the_segments():
    blank = np.asarray(process.draw_segments([], 20, 20))
    assert blank.min() == 255
    img = np.asarray(process.draw_segments(
        [], 20, 20, stud_ops=[("line", 2.0, 10.0, 18.0, 10.0, "edge")],
        stud_px=2))
    assert img[10, 10] < 128 and img[3, 10] == 255


def test_an_open_contour_run_draws_without_closing():
    img = np.asarray(process.draw_segments(
        [], 30, 30, contour_open=[[(2.0, 2.0), (28.0, 2.0), (28.0, 28.0)]],
        sil_px=2))
    assert img[2, 15] < 128 and img[15, 28] < 128
    assert img[15, 15] == 255                     # no closing diagonal
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_process.py -q -k "stud_ops or open_contour"`
Expected: FAIL (`TypeError: unexpected keyword argument 'stud_ops'`).

- [ ] **Step 3: Implement**:

```python
def _draw_op(dr, op, wpx, ss):
    """One line or arc op onto a supersampled canvas."""
    if op[0] == "line":
        _, x1, y1, x2, y2, _ = op
        dr.line([(x1 * ss, y1 * ss), (x2 * ss, y2 * ss)], fill=0, width=wpx)
        return
    _, cx, cy, ux, uy, vx, vy, t0, t1, _ = op
    n = max(2, int(abs(t1 - t0) / 2) + 2)
    pts = []
    for k in range(n):
        ang = math.radians(t0 + (t1 - t0) * k / (n - 1))
        c, s = math.cos(ang), math.sin(ang)
        pts.append(((cx + c * ux + s * vx) * ss, (cy + c * uy + s * vy) * ss))
    dr.line(pts, fill=0, width=wpx, joint="curve")


def draw_segments(segs, w, h, line_px=2, sil_px=2, supersample=3,
                  contour_rings=None, contour_px=None, studs=None,
                  stud_ops=(), stud_px=None, contour_open=()):
    """(existing docstring) `contour_open` are contour runs cut open where a
    placed stud hides them (instancing.cut_rings); `stud_ops` are placed
    studs' strokes (instancing.Instancer.png_ops), drawn last at `stud_px`."""
    ss = max(1, supersample)
    img = Image.new("L", (w * ss, h * ss), 255)
    dr = ImageDraw.Draw(img)
    cpx = max(1, round((contour_px if contour_px is not None else sil_px) * ss))
    for ring in contour_rings or []:
        pts = [(x * ss, y * ss) for x, y in ring]
        # re-append the first two points so the seam vertex gets a joint too
        dr.line(pts + pts[:2], fill=0, width=cpx, joint="curve")
    for run in contour_open or ():
        dr.line([(x * ss, y * ss) for x, y in run], fill=0, width=cpx,
                joint="curve")
    for op in segs:
        if len(op) == 5:                               # legacy line tuple
            op = ("line",) + tuple(op)
        _draw_op(dr, op, max(1, round(stroke_width(op, line_px, sil_px, studs)
                                      * ss)), ss)
    if stud_ops:
        wpx = max(1, round((line_px if stud_px is None else stud_px) * ss))
        for op in stud_ops:
            _draw_op(dr, op, wpx, ss)
    return img.resize((w, h), Image.LANCZOS)


def segments_mono(segs, w, h, line_px=2, sil_px=2, threshold=160,
                  contour_rings=None, contour_px=None, studs=None,
                  stud_ops=(), stud_px=None, contour_open=()):
    g = draw_segments(segs, w, h, line_px, sil_px,
                      contour_rings=contour_rings, contour_px=contour_px,
                      studs=studs, stud_ops=stud_ops, stud_px=stud_px,
                      contour_open=contour_open)
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")
```

- [ ] **Step 4: Run them** — `.venv/bin/python -m pytest tests/test_process.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/process.py tests/test_process.py
git commit -m "draw placed stud strokes and open contour runs in the PNG writer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: `Instancer` — one definition per stud, placed by both writers

**Files:** Modify `brick_icons/instancing.py`; Test `tests/test_instancing.py`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_instancing.py`)

```python
IDENT = primitives.Projection(RIGHT, UP, FWD, s=1.0, cx=0.0, cy=0.0, half=0.0)


def _inst(verdicts, monkeypatch, segs):
    plan = instancing.Plan(verdicts, (RIGHT, UP, FWD))
    res = hlr.VisResult([], (0.0, 0.0, 1.0, 1.0), 1.0, [], [], proj=IDENT,
                        studs=plan)
    inst = instancing.Instancer(res, "naive", LIB)
    lone = hlr.VisResult(segs, (0.0, 0.0, 1.0, 1.0), 1.0, [], [], proj=IDENT)
    monkeypatch.setattr(inst, "lone", lambda ref: lone)
    return inst


def _ref():
    return instancing.StudRef(1, Path("p/stud.dat"), np.eye(3), np.zeros(3),
                              16, 16, False)


def test_origin_fit_puts_the_reference_origin_on_canvas_zero():
    res = hlr.VisResult([], (0, 0, 1, 1), 4.0, [], [], proj=primitives.Projection(
        RIGHT, UP, FWD, s=4.0, cx=1.0, cy=2.0, half=50.0))
    k, kx, ky = hlr.canvas_affine(res, *instancing.origin_fit(res, 8.0))
    assert k == pytest.approx(8.0) and kx == pytest.approx(0.0) \
        and ky == pytest.approx(0.0)


def test_svg_and_png_place_the_same_stroke_ops(monkeypatch):
    v = instancing.Verdict(_ref(), "clear", hull=box(-6, -6, 6, 6), a=3.0, b=4.0)
    inst = _inst([v], monkeypatch, [("line", 0.0, 0.0, 1.0, 0.0, "edge")])
    svg = "".join(inst.svg_parts((2.0, 10.0, 20.0), 1.0))
    assert '<use href="#sd0s" x="16.00" y="28.00"/>' in svg
    assert '<line x1="0.00" y1="0.00" x2="2.00" y2="0.00" stroke-width="1.00"/>' in svg
    assert "sd0f" not in svg                              # no style, no fills
    assert inst.png_ops((2.0, 10.0, 20.0), 1.0) == [
        ("line", 16.0, 28.0, 18.0, 28.0, "edge")]


def test_a_cut_stud_is_clipped_alike_in_both_writers(monkeypatch):
    v = instancing.Verdict(_ref(), "cut", hull=box(-6, -6, 6, 6),
                           cover=box(0, -10, 10, 10))
    inst = _inst([v], monkeypatch, [("line", -4.0, 0.0, 4.0, 0.0, "edge")])
    svg = "".join(inst.svg_parts((1.0, 0.0, 0.0), 1.0))
    assert '<clipPath id="sc0">' in svg and '<g clip-path="url(#sc0)">' in svg
    [(kind, x1, y1, x2, y2, tag)] = inst.png_ops((1.0, 0.0, 0.0), 1.0)
    assert sorted([x1, x2]) == pytest.approx([-4.0, 0.0]) and y1 == y2 == 0.0


def test_the_contour_hides_behind_placed_studs(monkeypatch):
    clear = instancing.Verdict(_ref(), "clear", hull=box(-6, -6, 6, 6))
    inst = _inst([clear], monkeypatch, [])
    assert inst.hide_region((1.0, 0.0, 0.0), 2.0).area == pytest.approx(144.0)
    cut = instancing.Verdict(_ref(), "cut", hull=box(-6, -6, 6, 6),
                             cover=box(0, -10, 10, 10))
    inst = _inst([cut], monkeypatch, [])
    assert inst.hide_region((1.0, 0.0, 0.0), 2.0).area == pytest.approx(40.0)


def test_a_contour_ring_behind_a_stud_opens_into_one_run():
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    closed, runs = instancing.cut_rings([ring], box(4, -1, 6, 1))
    assert closed == [] and len(runs) == 1
    assert {tuple(runs[0][0]), tuple(runs[0][-1])} == {(4.0, 0.0), (6.0, 0.0)}
    closed, runs = instancing.cut_rings([ring], box(40, 40, 41, 41))
    assert closed == [ring] and runs == []


def test_clip_ops_cuts_arcs_and_lines_to_a_region():
    ops = [("line", -4.0, 0.0, 4.0, 0.0, "edge"),
           ("arc", 0.0, 0.0, 3.0, 0.0, 0.0, 3.0, 0.0, 360.0, "sil")]
    got = instancing.clip_ops(ops, box(-10, -10, 0, 10))
    assert got[0][0] == "line" and got[0][-1] == "edge"
    assert all(max(op[1], op[3]) <= 1e-9 for op in got)
    assert any(op[-1] == "sil" for op in got)
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_instancing.py -q -k "origin_fit or place_the_same or clipped_alike or hides_behind or opens_into or clip_ops"`
Expected: FAIL (`AttributeError: ... 'Instancer'`).

- [ ] **Step 3: Implement** — append to `brick_icons/instancing.py`. Extend the imports to `from . import geom2d, hlr, primitives, process, shade, sweep, timing, trace`, `from shapely import affinity` and `from shapely.geometry import LineString, MultiPoint, Polygon`.

```python
def canvas_geom(g, k, kx, ky):
    """A world-A/B geometry in canvas px."""
    return affinity.affine_transform(g, [k, 0.0, 0.0, k, kx, ky])


def origin_fit(res, k):
    """The (f, ox, oy) under which canvas_affine(res, ...) is (k, 0, 0): a
    lone stud's own drawing, its reference origin on canvas (0, 0)."""
    p = res.proj
    if p is None:
        return (k, 0.0, 0.0)
    f = k / p.s
    return (f, -(p.half - p.cx * p.s) * f, -(p.half - p.cy * p.s) * f)


def translate_op(op, dx, dy):
    if op[0] == "line":
        _, x1, y1, x2, y2, kind = op
        return ("line", x1 + dx, y1 + dy, x2 + dx, y2 + dy, kind)
    _, cx, cy, ux, uy, vx, vy, t0, t1, kind = op
    return ("arc", cx + dx, cy + dy, ux, uy, vx, vy, t0, t1, kind)


def clip_ops(ops, region, n=24):
    """Stroke ops cut to `region`, as line ops: what a PNG draws of a cut
    stud. An arc comes back as the chords of its sampled polyline, the way
    process.draw_segments samples one anyway."""
    shapely.prepare(region)
    out = []
    for op in ops:
        piece = LineString(process.op_points(op, n)).intersection(region)
        for g in getattr(piece, "geoms", [piece]):
            if g.geom_type != "LineString" or g.is_empty:
                continue
            c = list(g.coords)
            out += [("line", x1, y1, x2, y2, op[-1])
                    for (x1, y1), (x2, y2) in zip(c, c[1:])]
    return out


def cut_rings(rings, hide):
    """The silhouette contour a PNG draws, less where a placed stud hides
    it: (rings untouched, open runs left of the cut ones), canvas px."""
    if hide is None or hide.is_empty:
        return list(rings), []
    shapely.prepare(hide)
    closed, runs = [], []
    for ring in rings:
        pts = [tuple(map(float, p)) for p in ring]
        line = LineString(pts + pts[:1])
        if not shapely.intersects(line, hide):
            closed.append(ring)
            continue
        left = shapely.line_merge(line.difference(hide))
        for g in getattr(left, "geoms", [left]):
            if g.geom_type == "LineString" and not g.is_empty:
                runs.append(list(g.coords))
    return closed, runs


def _span(out, right, up, fwd):
    """The larger projected extent (LDU) of a flattened drawing."""
    pts = ([np.asarray(out["tri"], float).reshape(-1, 3)]
           if out["tri"] else [])
    pts += [np.asarray(e, float) for e in out["2"]]
    pts += [p.fit_pts() for p in out["analytic"]]
    if not pts:
        return 1.0
    a, b, _ = hlr.project(np.vstack(pts), right, up, fwd)
    return float(max(a.max() - a.min(), b.max() - b.min())) or 1.0


class Instancer:
    """Draws each distinct stud of a plan once and places it.

    `res` is the part's VisResult with `studs` set. A definition is the stud
    alone, run through `engine` -- the part's own pipeline, at the part's
    render scale -- cached by StudRef.key; its strokes and fills are fitted
    with origin_fit so the stud's reference origin is canvas (0, 0) at `k`
    px per LDU. Both writers place those same ops: `svg_parts` as `<use>`,
    `png_ops` translated and cut to shape."""

    def __init__(self, res, engine, ldraw_dir):
        self.res = res
        self.plan = res.studs
        self.engine = engine
        self.ldraw_dir = ldraw_dir
        self.roots = hlr.default_roots(ldraw_dir)
        self._lone, self._strokes = {}, {}

    def lone(self, ref):
        got = self._lone.get(ref.key)
        if got is not None:
            return got
        right, up, fwd = self.plan.basis
        out = {"2": [], "5": [], "tri": [], "tri_meta": [], "analytic": [],
               "printed": self.plan.printed}
        hlr.flatten(ref.path, ref.R, np.zeros(3), out, self.roots, depth=1,
                    inherited_invert=ref.invert, color=ref.color,
                    body=ref.body)
        for key in ("2_stud", "5_stud", "stud_refs", "studs"):
            out.pop(key, None)
        sweep.substitute(out)
        # the part's render px per LDU, so every pixel-sized tolerance in the
        # engine and its tail means what it meant for the part
        render_px = max(64, int(round(self.res.s * _span(out, right, up, fwd)))
                        + 20)
        with timing.phase("studs"):
            got = hlr.draw_flattened(out, right, up, fwd, render_px,
                                     cull=True, engine=self.engine)
        self._lone[ref.key] = got
        return got

    def strokes(self, ref, k):
        key = (ref.key, round(float(k), 9))
        if key not in self._strokes:
            lone = self.lone(ref)
            self._strokes[key] = hlr.affine_segments(lone.segs,
                                                     *origin_fit(lone, k))
        return self._strokes[key]

    def fills(self, ref, k, style, stud_px, crumb, weld_corners):
        if style is None:
            return []
        lone = self.lone(ref)
        if not lone.faces:
            return []
        fit = origin_fit(lone, k)
        with timing.phase("studs"):
            return shade.fill_ops(
                shade.apply_affine_faces(lone.faces, *fit), style, clip=True,
                ellipses=hlr.fit_ellipses(lone.ellipses, *fit),
                proj=lone.proj, fit=fit, refits=lone.refits, loops=lone.loops,
                strokes=self.strokes(ref, k), line_px=stud_px, sil_px=stud_px,
                weld_corners=weld_corners, ldraw_dir=self.ldraw_dir,
                crumb=crumb)

    def clip(self, v, k, kx, ky, pad):
        """A cut stud's clip, canvas px: its footprint grown by `pad` (its
        strokes' reach), less the planes in front of it."""
        return geom2d.difference(canvas_geom(v.hull, k, kx, ky).buffer(pad),
                                 canvas_geom(v.cover, k, kx, ky))

    def svg_parts(self, fit, stud_px, style=None, crumb=None,
                  weld_corners=False):
        """Elements for trace.segments_to_svg(between=...): one `<defs>`
        with each distinct stud's fill group (`sd<n>f`), stroke group
        (`sd<n>s`) and every cut stud's clip, then `<g class="studs">` of
        `<use>` pairs far to near -- fills then strokes, so a nearer stud
        covers a farther one's lines as the engine would. [] when nothing is
        placed."""
        placed = self.plan.placed()
        if not placed:
            return []
        k, kx, ky = hlr.canvas_affine(self.res, *fit)
        crumb = shade.RESIDUE_CRUMB if crumb is None else crumb
        defs, uses, ids, has_fill, clips = [], ['<g class="studs">'], {}, {}, 0
        for v in placed:
            if v.ref.key not in ids:
                n = ids[v.ref.key] = len(ids)
                fills = self.fills(v.ref, k, style, stud_px, crumb,
                                   weld_corners)
                has_fill[n] = bool(fills)
                if fills:
                    gdefs, body = trace.fill_elements(fills,
                                                      gid_prefix=f"sd{n}g")
                    defs += gdefs
                    defs.append(f'<g id="sd{n}f">' + "".join(body) + "</g>")
                defs.append(f'<g id="sd{n}s" stroke="black" fill="none" '
                            f'stroke-linecap="round">'
                            + "".join(trace.stroke_elements(
                                self.strokes(v.ref, k), stud_px, stud_px))
                            + "</g>")
            n = ids[v.ref.key]
            x, y = v.a * k + kx, v.b * k + ky
            pair = "".join(f'<use href="#sd{n}{layer}" x="{x:.2f}" y="{y:.2f}"/>'
                           for layer in (("f", "s") if has_fill[n] else ("s",)))
            if v.role == "cut":
                d = geom2d.path_d(self.clip(v, k, kx, ky, stud_px))
                if not d:
                    continue
                defs.append(f'<clipPath id="sc{clips}"><path d="{d}" '
                            f'clip-rule="evenodd"/></clipPath>')
                uses.append(f'<g clip-path="url(#sc{clips})">{pair}</g>')
                clips += 1
            else:
                uses.append(pair)
        return ["<defs>" + "".join(defs) + "</defs>"] + uses + ["</g>"]

    def png_ops(self, fit, stud_px):
        """The same strokes for a PNG under `fit`: translated to every placed
        stud, a cut one cut to its clip."""
        placed = self.plan.placed()
        if not placed:
            return []
        k, kx, ky = hlr.canvas_affine(self.res, *fit)
        ops = []
        for v in placed:
            moved = [translate_op(op, v.a * k + kx, v.b * k + ky)
                     for op in self.strokes(v.ref, k)]
            ops += (clip_ops(moved, self.clip(v, k, kx, ky, stud_px))
                    if v.role == "cut" else moved)
        return ops

    def hide_region(self, fit, sil_px):
        """Where the part's silhouette contour must not draw: behind a placed
        stud. A clear stud hides its whole footprint; a cut one what it shows,
        less half the contour's width, so the occluder's outline along the
        cut survives. None when nothing is placed."""
        k, kx, ky = hlr.canvas_affine(self.res, *fit)
        parts = []
        for v in self.plan.placed():
            g = canvas_geom(v.shown(), k, kx, ky)
            if v.role == "cut":
                g = g.buffer(-0.5 * sil_px)
            if not g.is_empty:
                parts.append(g)
        return geom2d.union_all(parts) if parts else None
```

- [ ] **Step 4: Run them** — `.venv/bin/python -m pytest tests/test_instancing.py -q`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/instancing.py tests/test_instancing.py
git commit -m "draw each distinct stud once and place it in the SVG and the PNGs, hiding the contour behind it" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: `--stud-instancing off|all`, wired through `process_one`

**Files:** Modify `brick_icons/config.py`, `brick_icons/cli.py`; Test `tests/test_config.py`, `tests/test_cli.py`, `tests/test_instancing.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_config.py`:

```python
def test_stud_instancing_defaults_off_and_takes_an_override():
    assert load_config(root="/proj").stud_instancing == "off"
    assert load_config(root="/proj",
                       overrides={"stud_instancing": "all"}).stud_instancing == "all"
```

Append to `tests/test_cli.py`:

```python
def test_render_tag_stamps_stud_instancing_when_it_is_on():
    cfg = cli._config_from_args(cli.build_parser().parse_args(
        ["3001", "--stud-instancing", "all"]))
    assert "studs=all" in cli.render_tag(cfg, "3001")
    cfg = cli._config_from_args(cli.build_parser().parse_args(["3001"]))
    assert "studs=" not in cli.render_tag(cfg, "3001")
```

Append to `tests/test_instancing.py`:

```python
SVG = ["--engine", "naive", "--format", "svg", "--shading", "outline",
       "--shade-style", "flat3"]


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_off_never_reaches_instancing_and_draws_as_the_default(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("--stud-instancing off reached brick_icons.instancing")
    monkeypatch.setattr(instancing, "withhold", boom)
    monkeypatch.setattr(instancing, "Instancer", boom)
    argv = ["3001", "--engine", "naive", "--format", "both", "--shading",
            "outline", "--shade-style", "flat3"]
    assert cli.main(argv + ["--out", str(tmp_path / "default")]) == 0
    assert cli.main(argv + ["--stud-instancing", "off",
                            "--out", str(tmp_path / "off")]) == 0
    for name in ("3001.svg", "3001.gray.png", "3001.mono.png"):
        assert (tmp_path / "default" / name).read_bytes() \
            == (tmp_path / "off" / name).read_bytes(), name


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_all_places_every_clear_stud_between_fills_and_strokes(tmp_path):
    assert cli.main(["3001", *SVG, "--stud-instancing", "all",
                     "--out", str(tmp_path)]) == 0
    svg = (tmp_path / "3001.svg").read_text()
    assert svg.count('<use href="#sd0s"') == 8 and svg.count('<use href="#sd0f"') == 8
    assert (svg.index('<g stroke-linejoin="round">') < svg.index('<g class="studs">')
            < svg.index('<g stroke="black"'))
    assert 'clip-path="url(#cclip)"' in svg          # contour hidden behind studs


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_translucent_and_wireframe_renders_draw_studs_through_the_engine(tmp_path):
    assert cli.main(["3001", *SVG, "--stud-instancing", "all", "--opacity", "0.5",
                     "--out", str(tmp_path / "t")]) == 0
    assert cli.main(["3001", "--engine", "naive", "--format", "svg", "--wireframe",
                     "--stud-instancing", "all", "--out", str(tmp_path / "w")]) == 0
    for d in ("t", "w"):
        assert "<use" not in (tmp_path / d / "3001.svg").read_text()


@pytest.mark.skipif(not HAVE_LIB, reason="LDraw library absent")
def test_the_pngs_and_the_physical_svg_place_studs_too(tmp_path):
    assert cli.main(["3001", "--engine", "naive", "--shading", "outline",
                     "--format", "png", "--mode", "both", "--stud-instancing", "all",
                     "--out", str(tmp_path / "p")]) == 0
    mono = np.asarray(Image.open(tmp_path / "p" / "3001.mono.png"))
    assert (mono == 0).any()
    assert cli.main(["3001", *SVG, "--scale-mode", "physical", "--stud-instancing",
                     "all", "--out", str(tmp_path / "m")]) == 0
    assert '<use href="#sd0s"' in (tmp_path / "m" / "3001.svg").read_text()
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/python -m pytest tests/test_config.py::test_stud_instancing_defaults_off_and_takes_an_override tests/test_cli.py::test_render_tag_stamps_stud_instancing_when_it_is_on tests/test_instancing.py -q -k "stud_instancing or off_never or all_places or translucent or physical"`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'stud_instancing'`; argparse rejects `--stud-instancing`).

- [ ] **Step 3: Implement.**

`config.py`: in `DEFAULTS` after `"crumb_ldu"`:

```python
    "stud_instancing": "off",  # off | all -- draw each declared stud once and
                               # place it wherever it shows (all), or every
                               # stud through the engine (off)
```

In `Config` after `crumb_ldu: float`, add `stud_instancing: str`. In `load_config`, after `crumb_ldu=...`, add `stud_instancing=str(data["stud_instancing"]),`.

`cli.py`:

- imports: `from . import render, process, trace, hlr, library, shade, geom2d, unwrap, instancing`
- parser, after `--crumb-ldu`:

```python
    p.add_argument("--stud-instancing", dest="stud_instancing",
                   choices=["off", "all"],
                   help="draw each declared stud once and place it wherever "
                        "it is clear or cut only by planes (all), or draw "
                        "every stud through the engine (off, the default); "
                        "translucent and wireframe renders are always off")
```

- `_config_from_args`: add `"stud_instancing": args.stud_instancing,` after `"crumb_ldu"`.
- `render_tag`, before `return`:

```python
    if cfg.stud_instancing != "off":
        bits.append(f"studs={cfg.stud_instancing}")
```

- a helper after `_sil_faces`:

```python
def _png_contour(inst, fit, sil_px, rings):
    """(closed rings, open runs) of the silhouette contour a PNG draws: the
    rings as they are, or cut open where a placed stud stands in front."""
    if inst is None or not rings:
        return rings, ()
    return instancing.cut_rings(rings, inst.hide_region(fit, sil_px))
```

- `process_one` (`cli.py:321-478`). The visible-segments call becomes:

```python
        res = hlr.visible_segments(part, cfg.ldraw_dir, lat=lat, long=long,
                                   render_px=cfg.render_px, cull=cull,
                                   engine=cfg.engine, pose=pose,
                                   canvas_px=None if cfg.scale_mode == "physical"
                                   else max(cfg.width, cfg.height),
                                   # a placed stud hides what is behind it,
                                   # so a render that draws hidden geometry
                                   # on purpose draws every stud itself
                                   stud_instancing=cfg.stud_instancing
                                   if cull else "off")
        segs, bbox, s = res.segs, res.bbox, res.s
        inst = (instancing.Instancer(res, cfg.engine, cfg.ldraw_dir)
                if res.studs is not None else None)
```

Physical SVG call: add after `debug_colors=cfg.debug_colors, studs=studs`:

```python
                    between=inst.svg_parts(
                        (f, ox, oy), studs.px if studs else cfg.line_mm / 0.4 * s,
                        style, crumb, cfg.weld_corners) if inst else None,
                    contour_hide=inst.hide_region(
                        (f, ox, oy), cfg.silhouette_mm / 0.4 * s) if inst else None)
```

Fit SVG call: add after `debug_colors=cfg.debug_colors`:

```python
                                      between=inst.svg_parts(
                                          icon_fit,
                                          studs.px if studs else line_px,
                                          style, crumb, cfg.weld_corners)
                                      if inst else None,
                                      contour_hide=inst.hide_region(icon_fit, sil_px)
                                      if inst else None)
```

Gray PNG:

```python
                gaff = hlr.fit_affine(bbox, gpx, gpx, cfg.margin, cfg.scale)
                gl, gs, gstuds = _stroke_tiers(cfg, res, basis, gaff,
                                               line_w, sil_w, stud_base, ratio)
                gsp = gstuds.px if gstuds else gl
                rings, runs = _png_contour(inst, gaff, gs,
                                           sil_rings(gpx, gpx, gfit, gs))
                g = process.draw_segments(gfit, gpx, gpx, line_px=gl, sil_px=gs,
                                          contour_rings=rings, contour_open=runs,
                                          studs=gstuds,
                                          stud_ops=inst.png_ops(gaff, gsp)
                                          if inst else (), stud_px=gsp)
```

Mono PNG:

```python
                msp = mstuds.px if mstuds else ml
                rings, runs = _png_contour(inst, icon_fit, ms, sil_rings(
                    cfg.width, cfg.height, mfit, ms))
                m = process.segments_mono(mfit, cfg.width, cfg.height,
                                          line_px=ml, sil_px=ms,
                                          contour_rings=rings, contour_open=runs,
                                          studs=mstuds,
                                          stud_ops=inst.png_ops(icon_fit, msp)
                                          if inst else (), stud_px=msp)
```

- [ ] **Step 4: Run them**

Run: `.venv/bin/python -m pytest tests/test_config.py tests/test_cli.py tests/test_lab_schema.py tests/test_instancing.py -q`
Expected: PASS (the lab schema picks the flag up with no other change).

- [ ] **Step 5: Commit**

```bash
git add brick_icons/config.py brick_icons/cli.py tests/test_config.py tests/test_cli.py tests/test_instancing.py
git commit -m "add --stud-instancing off|all, off by default and forced off for translucent and wireframe renders" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: The census carries the flag and the counts

**Files:** Modify `scripts/compare-silhouette-truth.py` (`drawn_as` ~119, `one` ~138, `main` ~214); Test `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (append to `tests/test_cli.py`)

```python
def test_the_census_names_stud_instancing_only_when_it_is_on():
    import argparse
    cst = _cst()
    base = dict(shade_style="flat3", line_width=0, silhouette_width=0,
                opacity=None)
    assert "stud_instancing" not in cst.drawn_as(
        argparse.Namespace(**base, stud_instancing="off"))
    assert cst.drawn_as(argparse.Namespace(
        **base, stud_instancing="all"))["stud_instancing"] == "all"
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_cli.py::test_the_census_names_stud_instancing_only_when_it_is_on -q`
Expected: FAIL (`KeyError: 'stud_instancing'`).

- [ ] **Step 3: Implement.** In `drawn_as`, before `return fields`:

```python
    if getattr(args, "stud_instancing", "off") != "off":
        fields["stud_instancing"] = args.stud_instancing
```

In `one`, append to `argv` before `"--out"`: `"--stud-instancing", args.stud_instancing,`. In `main` after `--silhouette-width`:

```python
    ap.add_argument("--stud-instancing", dest="stud_instancing",
                    choices=["off", "all"], default="off",
                    help="render with stud instancing; the row's counts then "
                         "carry studs_clear/cut/hidden/fallback")
```

The counts themselves need no change: `withhold` writes them through `timing.count`, and `one` already copies `timing.counts()` into `row["counts"]` (`compare-silhouette-truth.py:194`).

- [ ] **Step 4: Run it** — same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/compare-silhouette-truth.py tests/test_cli.py
git commit -m "let the census render with --stud-instancing and name it in the row" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: `vet-goldens --after-args` — two flag sets at one revision

**Files:** Modify `scripts/vet-goldens.py` (`render` ~69, `run_here` ~150, `run_fleet` ~267, `main` ~307); Create `tests/test_vet_goldens.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_vet_goldens.py`:

```python
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _vg():
    spec = importlib.util.spec_from_file_location(
        "vet_goldens", ROOT / "scripts" / "vet-goldens.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_appends_the_side_s_extra_flags_before_out(tmp_path, monkeypatch):
    vg = _vg()
    seen = {}

    class Done:
        returncode, stderr, stdout = 1, "boom", ""

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        return Done()
    monkeypatch.setattr(vg.subprocess, "run", fake)
    case = {"id": "3001", "part": "3001", "args": ["--shading", "outline"]}
    png, err, _ = vg.render(case, tmp_path, "occt", tmp_path, 64,
                            extra=["--stud-instancing", "all"])
    assert png is None and err == "boom"
    assert seen["cmd"][-4:-2] == ["--stud-instancing", "all"]
    assert seen["cmd"][-2] == "--out"
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_vet_goldens.py -q`
Expected: FAIL (`TypeError: render() got an unexpected keyword argument 'extra'`).

- [ ] **Step 3: Implement.** Add `import shlex`. Then:

```python
def render(case, tree: Path, engine: str, dest: Path, width: int,
           timeout: float | None = None, extra=()):
    ...
            [sys.executable, "-m", "brick_icons.cli", case["part"],
             "--engine", engine, *case["args"], *extra, "--out", str(work)],
```

In `run_here`: after `after_name = ...` add

```python
    after_extra = shlex.split(a.after_args or "")
    if after_extra:
        after_name += f" [{a.after_args}]"
```

and in `one`: `f = render(case, ROOT, a.engine, out / "after", width, a.timeout, after_extra)`. Add `"after_args": a.after_args,` to the `report` dict. In `run_fleet`, after the timeout line: `if a.after_args: cmd += [f"--after-args={a.after_args}"]`. In `main`:

```python
    ap.add_argument("--after-args", dest="after_args",
                    help="flags added to every `after` render only; with "
                         "--base HEAD this compares two flag sets at one "
                         "revision (pass as --after-args='--flag value')")
```

Extend the module docstring with one usage line:
`.venv/bin/python scripts/vet-goldens.py --parts batch.txt --base HEAD --after-args='--stud-instancing all'`

- [ ] **Step 4: Run it** — same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/vet-goldens.py tests/test_vet_goldens.py
git commit -m "let vet-goldens add flags to the after side, to compare two flag sets at one revision" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Interleaved off/all timing script

**Files:** Create `scripts/stud-ab-timing.py`; Create `tests/test_stud_ab_timing.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_stud_ab_timing.py`:

```python
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _mod():
    spec = importlib.util.spec_from_file_location(
        "stud_ab_timing", ROOT / "scripts" / "stud-ab-timing.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_rows_are_medians_of_interleaved_draws(tmp_path, monkeypatch):
    mod = _mod()
    calls = []

    def fake(part, mode, a, out):
        calls.append(mode)
        return (2.0 if mode == "off" else 1.0), {"studs_clear": 8, "faces_healed": 1}
    monkeypatch.setattr(mod, "draw", fake)
    sink = tmp_path / "t.jsonl"
    assert mod.main(["3001", "--reps", "1", "--jsonl", str(sink)]) == 0
    assert calls == ["off", "off", "all", "all", "off"]      # warm-up, then ABBA
    row = json.loads(sink.read_text())
    assert (row["off"], row["all"], row["ratio"]) == (2.0, 1.0, 0.5)
    assert row["counts"] == {"studs_clear": 8}
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_stud_ab_timing.py -q`
Expected: FAIL (`FileNotFoundError` for the script).

- [ ] **Step 3: Implement** — create `scripts/stud-ab-timing.py`:

```python
#!/usr/bin/env python3
"""What stud instancing costs or saves, per part, on one machine.

    .venv/bin/python scripts/stud-ab-timing.py --engine occt --reps 2 \
        --jsonl out/stud-ab/occt.jsonl 3811 3867 41539 3036 3958 3001

Draws each part with `--stud-instancing off` and `all` in one process,
interleaved A B B A per rep, after one untimed draw that fills the mesh
cache. A sequential A/B measures the node's load, not the code; interleaving
part by part lands any drift on both sides alike. Prints one line per part --
median seconds each way, the ratio, the stud counts -- and appends the same
as a JSON row to --jsonl.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from brick_icons import cli, timing  # noqa: E402


def draw(part, mode, a, out):
    argv = [part, "--format", "svg", "--shading", "outline",
            "--shade-style", a.shade, "--engine", a.engine, "--angle", "iso",
            "--stud-instancing", mode, "--root", str(ROOT), "--out", str(out)]
    cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
    timing.reset()
    t0 = time.perf_counter()
    cli.process_one(cfg, part, out)
    return time.perf_counter() - t0, timing.counts()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parts", nargs="*")
    ap.add_argument("--list", help="file of part[<TAB>label] lines")
    ap.add_argument("--engine", default="occt")
    ap.add_argument("--shade", default="flat3")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--jsonl")
    a = ap.parse_args(argv)
    parts = list(a.parts)
    if a.list:
        parts += [ln.split("\t")[0].strip()
                  for ln in Path(a.list).read_text().splitlines()
                  if ln.strip() and not ln.startswith("#")]
    if not parts:
        ap.error("name at least one part, or pass --list")
    sink = Path(a.jsonl) if a.jsonl else None
    if sink:
        sink.parent.mkdir(parents=True, exist_ok=True)
    print(f"{'part':>10} {'off s':>8} {'all s':>8} {'all/off':>8}  studs",
          flush=True)
    for part in parts:
        secs, counts = {"off": [], "all": []}, {}
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            try:
                draw(part, "off", a, out)               # warm-up: mesh cache
                for _ in range(a.reps):
                    for mode in ("off", "all", "all", "off"):
                        s, c = draw(part, mode, a, out)
                        secs[mode].append(round(s, 3))
                        if mode == "all":
                            counts = {k: v for k, v in c.items()
                                      if k.startswith("studs_")}
            except Exception as e:
                print(f"{part:>10} FAILED {type(e).__name__}: {e}", flush=True)
                continue
        off = statistics.median(secs["off"])
        on = statistics.median(secs["all"])
        row = {"part": part, "engine": a.engine, "off": off, "all": on,
               "ratio": round(on / off, 3) if off else None,
               "counts": counts, "runs": secs}
        studs = " ".join(f"{k[6:]}={v}" for k, v in sorted(counts.items()))
        print(f"{part:>10} {off:8.2f} {on:8.2f} {row['ratio']:8.3f}  {studs}",
              flush=True)
        if sink:
            with sink.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run it** — same command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/stud-ab-timing.py tests/test_stud_ab_timing.py
git commit -m "add stud-ab-timing.py, which times --stud-instancing off against all interleaved per part" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: Run the affected tests; prove `off` draws as before

**Files:** none

- [ ] **Step 1: Unit and integration files**

Run: `.venv/bin/python -m pytest tests/test_instancing.py tests/test_hlr.py tests/test_primitives.py tests/test_sweep.py tests/test_trace.py tests/test_process.py tests/test_config.py tests/test_cli.py tests/test_lab_schema.py tests/test_vet_goldens.py tests/test_stud_ab_timing.py -q`
Expected: PASS.

- [ ] **Step 2: occt tests on the fleet** (`tests/test_occt.py` runs for minutes). Use the `onto-test` skill to run `tests/test_occt.py` on a node. Expected: PASS.

- [ ] **Step 3: Naive byte gate** — `BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py -q` locally (PASS). Then the full gate on a node, with the Bash sandbox disabled for `onto`:

```bash
onto status
onto run --detach --timeout 1h --task stud-goldens-full --kind score \
  --icon chart.line.text.clipboard --in brick-icons \
  --env PATH=/opt/homebrew/bin:/usr/bin:/bin --env BRICK_GOLDENS=full \
  msb-uai -- .venv/bin/python -m pytest tests/test_goldens.py -q
```
(Put the node `onto status` names with free cores in place of `msb-uai`.) Expected: PASS: the naive engine under `off` is byte-identical to the frozen goldens.

- [ ] **Step 4: occt off against Task 0's baseline**

```bash
.venv/bin/python -m brick_icons.cli 3001 3941 --engine occt --format svg \
  --shading outline --shade-style flat3 --stud-instancing off --out out/stud-off-after
for p in 3001 3941; do
  resvg --width 512 out/stud-baseline/$p.svg out/stud-baseline/$p.png
  resvg --width 512 out/stud-off-after/$p.svg out/stud-off-after/$p.png
done
.venv/bin/python -c "
from PIL import Image
from brick_icons.lab import diff
def flat(p):
    im = Image.open(p).convert('RGBA'); bg = Image.new('RGBA', im.size, 'white')
    bg.alpha_composite(im); return bg.convert('RGB')
for p in ('3001', '3941'):
    _img, comps, px = diff.panel(flat(f'out/stud-baseline/{p}.png'), flat(f'out/stud-off-after/{p}.png'))
    print(p, comps, 'components', px, 'px'); assert comps == 0, p
"
```
Expected: `0 components` for both. Byte equality (`shasum -c out/stud-baseline/SHA256` after copying) is a bonus; occt is not byte-stable run to run (`db._same_pixels`).

---

### Task 16: Vet `all` against `off` on the batch

**Files:** `out/stroke-batch.txt` (gitignored input)

- [ ] **Step 1: Place the part list.** The spec's 197-part batch is `part<TAB>label` per line (the first is part `51542`, label `0.22 px/LDU, studs`), saved in the planning session's scratchpad:

```bash
cp /private/tmp/claude-501/-Users-mike-src-brick-icons/8e63426a-3dba-4402-ab9f-a8bcc4e7cc5d/scratchpad/stroke-batch.txt out/stroke-batch.txt
wc -l out/stroke-batch.txt
```
Expected: `197 out/stroke-batch.txt`. If the scratchpad copy is gone, stop and ask for the list; do not substitute another.

- [ ] **Step 2: Everything committed** — `git status --porcelain -- brick_icons scripts` must print nothing. With `--base HEAD`, `before` and `after` then differ only by the flag.

- [ ] **Step 3: occt** (sandbox disabled; runs on the fleet through `onto do`):

```bash
.venv/bin/python scripts/vet-goldens.py --parts out/stroke-batch.txt --source occt \
  --engine occt --base HEAD --after-args='--stud-instancing all' \
  --label stud-inst-occt --timeout 1200
```

- [ ] **Step 4: naive**

```bash
.venv/bin/python scripts/vet-goldens.py --parts out/stroke-batch.txt --source naive \
  --engine naive --base HEAD --after-args='--stud-instancing all' \
  --label stud-inst-naive --timeout 1200
```

- [ ] **Step 5: Fallback rate per part** (census counts):

```bash
cut -f1 out/stroke-batch.txt > out/stroke-batch-ids.txt
onto run --detach --timeout 4h --task stud-census --kind score \
  --icon chart.line.text.clipboard --in brick-icons \
  --env PATH=/opt/homebrew/bin:/usr/bin:/bin \
  --out out/stud-census --to out/stud-census msb-uai -- \
  .venv/bin/python scripts/compare-silhouette-truth.py --list out/stroke-batch-ids.txt \
  --engine occt --stud-instancing all --jsonl out/stud-census/occt.jsonl
```
When it is fetched:
```bash
.venv/bin/python -c "
import json
for ln in open('out/stud-census/occt.jsonl'):
    r = json.loads(ln); c = r.get('counts') or {}
    n = sum(c.get(f'studs_{k}', 0) for k in ('clear','cut','hidden','fallback'))
    if n: print(f\"{r['part']:>10} {n:5d} studs  fallback {c.get('studs_fallback',0):4d} ({100*c.get('studs_fallback',0)/n:.0f}%)  cut {c.get('studs_cut',0)}  hidden {c.get('studs_hidden',0)}\")
"
```

- [ ] **Step 6: Review.** Post every `out/vet/stud-inst-*/sheet-*.png` to the wall. Each sheet's title names the flag through `after_name`. Diffs are expected only as antialias noise plus two changes: back-row studs now outlined at the stud weight instead of the contour weight (the fix for `3001-contour-studs-at-line-weight`), and 51542's stud walls filled (`51542-stud-walls-unfilled`). Any other moved region stops the change; investigate with superpowers:systematic-debugging. Record the counts and sheet paths in the `notes` of both defects in `tests/goldens/defects.toml`, then commit:

```bash
git add tests/goldens/defects.toml
git commit -m "record the stud instancing vet on its two defects" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 17: Timing A/B on one node

**Files:** none (output `out/stud-ab/`)

- [ ] **Step 1: Launch** (sandbox disabled; one node for the whole run, so both sides see one machine):

```bash
onto status
onto run --detach --timeout 4h --task stud-ab-timing --kind score \
  --icon chart.line.text.clipboard --in brick-icons \
  --env PATH=/opt/homebrew/bin:/usr/bin:/bin \
  --out out/stud-ab --to out/stud-ab msb-uai -- \
  .venv/bin/python scripts/stud-ab-timing.py --engine occt --reps 2 \
  --jsonl out/stud-ab/occt.jsonl 3811 3867 51542 41539 3036 3958 3033 4282 3001 3941
```

- [ ] **Step 2: Read the per-part table** from the job log (`onto jobs`, then its log), or from `out/stud-ab/occt.jsonl` once fetched. Every part should show `all/off` below 1 for baseplates. A part above 1 is a finding: report it; do not tune it away.

---

### Task 18: Spec status and HANDOFF

**Files:** Modify `docs/superpowers/specs/2026-09-27-stud-instancing-design.md:3-5`, `HANDOFF.md` (top)

- [ ] **Step 1: Spec status line.** Replace the "**Status: designed 2026-09-27, not built.** ..." paragraph with:

```markdown
**Status: built behind `--stud-instancing` (default `off`) -- see
`brick_icons/instancing.py`.** One difference from the text below: a cut
stud's clip is taken from the occluding primitive's outline or the coplanar
triangles the samples hit, before the engine runs, not from the engine's
fitted face polygons -- classification has to precede the engine.
```

- [ ] **Step 2: HANDOFF.** Add a section at the top of `HANDOFF.md`, filled from Tasks 16 and 17. Use the real numbers from `out/vet/stud-inst-*/report.json`, the census summary and `out/stud-ab/occt.jsonl`; paste the timing table as printed.

```markdown
## 2026-09-2x: stud instancing built, behind --stud-instancing (off)

`--stud-instancing all` classifies every declared stud before the engine runs
(clear / cut / hidden / fallback, counted in the census `counts` as
`studs_*`), keeps each placed stud as an occluder, draws one definition per
(file, basis, color, body, winding) through the part's own engine and places
it: `<use>` in the SVG, translated strokes in the PNGs. Translucent and
wireframe renders are always off. The part contour is hidden behind placed
studs, so a stud on the outline draws its own outline at the stud weight.

Vetted on the 197-part batch `out/stroke-batch.txt`: occt <N moved / sheet path>, naive <...>.
Fallback rate: <per-part summary>. Timing, one node, interleaved:
<table from stud-ab-timing.py>.

Next: decide whether `all` becomes the default, then fill `occt-svelte`
(its fill was held for this).
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-09-27-stud-instancing-design.md HANDOFF.md
git commit -m "mark stud instancing built behind its flag, and hand off its vet and timing" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Critical Files for Implementation
- /Users/mike/src/brick-icons/brick_icons/instancing.py (new)
- /Users/mike/src/brick-icons/brick_icons/hlr.py
- /Users/mike/src/brick-icons/brick_icons/occt.py
- /Users/mike/src/brick-icons/brick_icons/cli.py
- /Users/mike/src/brick-icons/brick_icons/trace.py
