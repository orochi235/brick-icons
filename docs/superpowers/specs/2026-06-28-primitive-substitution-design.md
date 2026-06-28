# Design: Analytic primitive substitution (path B) for HLR outlines

Status: proposed (2026-06-28). Builds on
`2026-06-28-hlr-outline-design.md` (the faceted HLR renderer now on `main`).

## Why

The HLR outline renderer produces clean line art, but residual artifacts on
*curved* parts trace to the **rasterized z-buffer**: it cannot represent depth
precisely at a silhouette tangent, so faceted curved surfaces self-occlude with
quantization fuzz. Symptoms (see the faceted-HLR handoff):

- **3941 (round 2×2) base gap** — the body's vertical silhouette doesn't connect
  to the bottom-rim arc; bottom-rim edges self-occlude against the faceted front
  wall at the tangent. The `EDGE_BIAS` bump fixes it but leaks stray lines; the
  `dilate_zbuffer` neighborhood-max fixes it at `render_px≈900` without leak but
  is **resolution-fragile** (does not fully connect at production `render_px=2048`).
- **"Tails"** around 3941's center notch at high edge bias.

Root finding (verified in LDraw source): LDraw curved geometry is **polygonal,
not curve patches** — a cylinder is 4× quarter-cylinder = 48 flat quads in
`p/48/`. The smooth silhouettes we already get come from authored **type-5
conditional lines**, not from the surfaces. So the *drawn curves* are already
smooth, but the *occlusion* against faceted surfaces is not.

## Decision

**Acceptance bar: geometrically exact curves — no quantization at any resolution,
by construction.** Substitute LDraw's named curved primitives with their exact
analytic shapes, and replace the rasterized z-buffer with a **continuous analytic
depth oracle**. Output curves as **true SVG elliptical-arc commands** (the goal is
clean, scalable SVG). Faceted recursion remains the fallback for unrecognized
primitives, so the change is incremental and never breaks unknown parts.

This is "Approach 1 — analytic depth oracle" (chosen over full event-based
analytic HLR, which is far more complex for no benefit at icon sizes, and over a
hi-res tessellated depth buffer, which would reintroduce the raster quantization
we are removing).

## Primitive inventory (curated `parts.txt`)

Recursive scan of the curated set, most-referenced curved primitives:

```
1-4edge (1040)  1-4cyli (536)  4-4edge (253)  4-4cyli (134)  4-4disc (63)
4-4ring3 (28)   1-16chrd (16)  2-4edge (14)   4-4ndis (12)   1-8chrd (12)
2-4ndis (10)    4-4ring2 (10)  2-4cyli (9)    1-8edge (8)    3-4edge (8)
1-4cyls (6)     axlehol2 (5)   1-8cyli (4)    4-4cylo (4)    3-4cyli (4)
3-4disc (4)     4-4ring4 (4)   ... axlehol*/axl* composites, ring1
```

Families: **edge** (drawn circle arc; no surface), **cyli/cyls/cylo** (cylinder
wall), **disc** (filled circular face), **ndis** (square-minus-quarter-disc corner
fill), **ring1–4** (flat annulus), **chrd** (chord line), **con** (cone). The
`axlehol*`/`axl*` composites reference these leaves and are covered automatically
by substituting at the leaf level.

## Architecture

New module **`primitives.py`** owns all analytic shape knowledge and math.
`hlr.py` remains the scene/pipeline orchestrator. Boundary: `primitives.py` knows
*shapes*; `hlr.py` knows the *scene*.

### 1. Recognition + parameterization

LDraw curved primitives are authored in canonical local frames (radius 1; unit
height along local **Y** for cylinders/cones; radius-1 circle in the local **XZ**
plane for discs/edges/rings). The part's accumulated `(R, t)` transform
places/scales/orients them. So a substitution record carries only:

```
{ kind, sector_deg, R, t }
```

— no baked geometry. The basename encodes kind and angular sector:
`1-4cyli`→(cylinder, 90°), `1-8edge`→(edge, 45°), `3-4disc`→(disc, 270°), etc.
A parser maps `basename → (kind, sector_deg)`. The arc's **start angle is
canonical** (LDraw authors each fraction from a fixed orientation, sweeping the
sector in local +X→+Z); the part's `R` supplies the actual world orientation, so
no per-record start angle is stored.

### 2. Substitution hook in `flatten`

Today a type-1 reference resolves and recurses. New behavior: if the resolved
basename is a recognized curved primitive, **append an analytic record to a new
`out["analytic"]` bucket and stop descending** that reference. Otherwise recurse
as today. Consequences:

- recognized **surface** (cyli/cyls/cylo/disc/ndis/ring/con) → an analytic
  *occluder*, plus analytic *drawn curves* where it has a silhouette;
- recognized **edge/chrd** → a drawn curve only (no occluder);
- **unrecognized curved primitive → falls through to today's polygon recursion**
  (faceted, but never broken).

Brick bodies and any non-substituted geometry keep flowing into the existing
`"2"/"5"/"tri"` buckets — still exact flat polygons, still occluders and edges.

### 3. Exact projection + curve emission

A primitive circle is `C + r(cosθ·U + sinθ·V)` in 3-D, where `C, U, V` are the
canonical center and local X/Z basis under `(R, t)`. Orthographic projection is
linear, so it maps to an exact 2-D ellipse `c + cosθ·u + sinθ·v` (`u, v` the
projected basis vectors) for all θ — exact at any resolution. Emission per kind:

- **edge / disc boundary / ring boundary**: ellipse arc over `[θ0, θ0+sector]`.
- **cylinder side silhouette**: under orthographic projection the outline is two
  straight lines tangent to the projected end-ellipses, parallel to the projected
  axis, plus the visible cap arcs. The two tangent θ are where the surface normal
  is perpendicular to the view direction — closed form from the projected axis and
  radius. This synthesizes the silhouette that type-5 conditionals used to give
  for substituted parts.

### 4. The occlusion oracle (the crux)

Replace the rasterized z-buffer with a continuous `depth_at(x, y)`: shoot the
orthographic view ray through screen point `(x, y)` and return the nearest
occluder depth, or miss. All closed-form per occluder:

- **flat triangle** (brick bodies + non-substituted faces): point-in-triangle +
  barycentric depth, evaluated per query (the current rasterizer's math, gridless).
- **cylinder**: ray vs infinite cylinder (quadratic in local frame), clamp hit to
  height extent and angular sector, take nearer root.
- **disc / ring / ndis**: ray-plane hit, then radius / annulus / square-minus-
  quarter-disc region test (+ sector).
- **cone**: ray vs cone quadric, clamp to height.

Depth field = `min` over occluders. A drawn-curve sample is visible iff
`sample_depth ≤ field + ε`.

**This retires the bias/dilation hacks.** `EDGE_BIAS`, `SIL_BIAS`, and the whole
resolution-fragile `dilate_zbuffer` exist only because the raster z-buffer can't
represent depth precisely at a silhouette tangent — that *is* the 3941 base gap.
With an exact analytic depth field the tangent is exact, so the gap cannot form.
`ε` shrinks to a vanishing fraction of the model depth range (resolution-
independent) and is needed only so a curve doesn't self-occlude against the
surface it lies on. Cleanest rule: **exclude a curve's owning primitive from its
own occluder test**, making `ε` effectively zero. Owning-primitive tracking is the
one new piece of state.

### 5. Output — true SVG elliptical arcs

Generalize the drawn-output model from line segments to **draw ops**:

```
("line", x1, y1, x2, y2, kind)
("arc",  cx, cy, rx, ry, phi, theta0, theta1, kind)    # kind ∈ edge | sil
```

Visibility is computed per op by sampling against the oracle, which may split one
arc into several visible sub-arcs (each with its own `theta0/theta1`).

- **`trace.segments_to_svg`**: emit `<line>` for line ops and SVG path `A`
  (elliptical-arc) commands for arc ops — analytically exact, infinitely scalable.
- **`process.draw_segments`**: rasterize arc ops by sampling the ellipse finely
  into the existing supersampled polyline draw (sampling density is our choice →
  visually exact). mono/gray paths unchanged downstream.
- **`hlr.fit_segments`**: transform op endpoints/centers; arcs scale uniformly
  under the existing contain/center fit (uniform scale + translate preserves
  ellipse arcs; `rx, ry` scale by the fit factor).

### 6. CLI / config

No public surface changes. `--shading outline` still routes through
`hlr.visible_segments`, same camera / fit / widths. Substitution is internal.

## Module boundaries

- **`primitives.py`** (new): name→`(kind, sector)` parser; per-kind
  `drawn_curves(project_fn)` → arc/line ops; per-kind `depth_at(x, y, ray)` →
  depth | miss. One responsibility: analytic shapes ↔ math.
- **`hlr.py`**: `flatten` gains the substitution hook + `out["analytic"]`;
  `visible_segments` builds the occluder set (flat tris + analytic surfaces),
  collects drawn ops (existing type-2/5 for non-substituted geometry + analytic
  ops), tests visibility against the analytic depth field, returns draw ops + bbox.
  Retires `dilate_zbuffer`, `EDGE_DILATE`, and the large relative biases.
- **`trace.py`**: `segments_to_svg` learns line + arc ops.
- **`process.py`**: `draw_segments`/`segments_mono` learn to sample arc ops.

## Testing (TDD)

Pure-geometry units run without the vendor library:

- name→shape parser: family + sector degrees for each inventory name.
- circle→ellipse exactness: a known `(R, t)` → projected points match the analytic
  ellipse.
- cylinder silhouette: tangent θ and the two side lines for an axis-aligned and a
  tilted cylinder.
- depth oracle per type: ray hit/miss, cap/sector clamping, nearer-root selection.
- occlusion correctness: a disc in front hides the correct arc interval.
- **3941 tangent regression**: assert the base silhouette connects to the rim arc
  (no gap) at **both** `render_px=900` and `2048` — the artifact becomes a guard.
- fallback: an unrecognized curved name still recurses to polygons and renders.
- end-to-end on 3941 / 3701, **skipped if `vendor/ldraw` absent** (matches existing
  render/trace tests).

## Validation targets

- 3941 base gap closed **and resolution-stable** (the headline win).
- "tails" around 3941's notch gone.
- Regenerate the 24-part gray batch sheet; eyeball on the **gray masters**
  (`*.gray.png`), not the 1bpp mono.
- **Top-corner stud spurs are tracked separately** — the handoff flags them as
  possibly unrelated to faceting/occlusion. Diagnose independently; do not assume
  path B fixes them.

## Scope / out of scope

- **In:** the primitive families in the inventory (cyli/cyls/cylo, disc, ndis,
  edge, chrd, ring1–4, con; axle-holes via leaf decomposition). Exact arc SVG
  output. Analytic depth oracle covering analytic surfaces + flat triangles.
- **Out:** full event-based analytic HLR (curve–curve intersection / interval
  walking); cel/normal/color shadings (still LDView); curved primitives outside
  the curated set (fall back to faceted recursion).

## Reference

LGEO (LDraw→POV primitive substitution) for the name→shape mapping precedent.
Faceting reference: `vendor/ldraw/p/48/1-4cyli.dat` (12 quads + 13 conditional
lines per quadrant), `p/48/4-4cyli.dat` (4× `1-4cyli`).
