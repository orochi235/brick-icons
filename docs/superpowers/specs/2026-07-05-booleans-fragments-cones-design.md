# Design: polygon booleans, visible-fragment clipping, analytic cones/ndis

Status: proposed (2026-07-05). Builds on
`2026-07-03-scaled-svg-library-and-shading-design.md` (flat3 shading now on
`feat/scaled-svg-library-shading`) and the boundary-merge post-mortem
(2026-07-05, reverted; tree kept at eeb6587).

## Why

The project philosophy is **few, exact, meaningful SVG elements** — one element
per visually continuous surface. The current fill layer violates it two ways:

1. **Facet clouds.** Smooth faceted curves (3960's dish, 50950's slope, cone
   bodies) emit one `<path>` per camera-facing triangle. The shared
   `userSpaceOnUse` gradient makes them *look* continuous, but the SVG is a
   cloud of tiny paths.
2. **Hidden overdraw.** Painter's algorithm emits every face, including ones
   entirely covered by nearer faces. The hidden elements bloat files and are
   semantically wrong (elements that are never visible).

The naive fix — tracing facet-group boundaries by cancelling shared edges —
was attempted and reverted. Three hard walls (all confirmed empirically):
T-junction tessellations (3960 mixes 16- and 48-segment rings, so interior
edges have no matching partner), fragile undirected edge-chaining, and
projected self-overlap of curved groups near the silhouette (a single evenodd
path cannot represent it; edge cancellation double-counts it).

All three walls fall to **robust 2-D polygon booleans**: union is defined on
T-junctions and self-overlaps, and the same dependency gives **difference**,
which solves hidden overdraw exactly (clip each face to its visible fragment).
Separately, the biggest remaining facet clouds are cone bodies — LDraw has
*named* cone primitives (`n-dconN`), so extending analytic substitution
(as already done for cyli/disc/ring) removes those clouds at the source and
gives exact occlusion. `ndis` (square-minus-disc corner fill) is the last
recognized-but-unsubstituted flat primitive in the curated set. This spec
treats the three as one package, per the post-mortem.

## Decisions (alternatives considered)

- **Boolean engine: shapely 2.x** (GEOS). Chosen over pyclipper (integer
  scaling dance, clunky multi-polygon/hole handling) and pure-Python libraries
  (unacceptable robustness). Shapely gives `unary_union`, `difference`,
  `set_precision` (snap-to-grid robustness), `make_valid`, STRtree — one
  dependency serving both union and difference. New dep in `pyproject.toml`.
- **Fragment clipping in `fill_ops`** (post-affine, SVG-only path). Fills are
  consumed nowhere else; PNG gray/mono use only stroke segments. Booleans in
  one place; `hlr.py` untouched except new occluder kinds.
- **Order first, clip second, merge third.** `order_faces` (witness-depth
  ordering) stays per-facet and untouched — it already answers "who is nearer"
  robustly, including curved own-occluder refinement. Clipping consumes its
  paint order; merging operates on the resulting *disjoint* fragments, where
  paint order is no longer load-bearing. Alternative (merge groups before
  ordering) rejected: a merged group is non-planar, so witness depth would need
  per-member dispatch — more machinery for no output difference.
- **Cone occluder is a new class**, not a generalization of the battle-tested
  `CylinderOccluder` (memory: gotchas if the cull/ordering path is touched).
  Wall-face *builders* in `shade.py` do share helpers, parameterized by
  per-level radius. Unification of the occluders is possible later.
- **Dish surfaces stay faceted** — there is no named dish primitive (3960's
  curve is hand-authored quads in `s\3960s02/s04`); the union merge is the fix
  for them. (The post-mortem's "analytic dish" hope was wrong: nothing to
  substitute.)

## Architecture

New module **`geom2d.py`** isolates shapely:

- `to_geom(poly, holes=None)` — ndarray ring(s) → cleaned shapely Polygon
  (`set_precision(grid)`, `make_valid` fallback). Grid ~1e-3 px.
- `union_all(geoms)`, `difference(a, b)` — thin, exception-safe wrappers
  (a GEOS topology error on a degenerate sliver must never kill a render;
  fall back to the unclipped input and warn).
- `path_d(geom)` — Polygon/MultiPolygon → single SVG `d` string with one
  subpath per ring (exteriors + holes), for `fill-rule="evenodd"`.
- `area(geom)`.

### 1. Analytic cones (`primitives.py`)

`parse_primitive` learns `con`: `n-dconN` → kind `"con"`, sector `360*n/d`,
`inner = N` (reusing the numeric slot: ring→inner radius, con→top radius).
Geometry (verified against `p/1-4con4.dat`): truncated cone, radius `N+1` at
local y=0 → radius `N` at y=1. `con0` reaches an apex.

**`ConeOccluder`** works in the primitive's local frame (`Minv = R⁻¹`), which
handles scaling and shear uniformly: transform ray `(O, F)` to local, solve
`(ox+λfx)² + (oz+λfz)² = (N+1 − oy − λfy)²` (quadratic in λ; the ray parameter
λ is invariant under the linear map, so roots are world depths directly).
Clamp hits to `y ∈ [0,1]` and the angular sector. Same API as
`CylinderOccluder`: `depth`, `depth_far(clamp=...)` (needed for interior
far-half wall ordering).

**Silhouette generators.** Local cone normal along a generator is constant:
`m(θ) = (cosθ, 1, sinθ)` (cylinder's is `(cosθ, 0, sinθ)`). World condition
`n·fwd = 0` reduces to `A cosθ + B sinθ = C` with `(A, _, B) = g = Minv·fwd`,
`C = −g_y`: zero, one, or two solutions `θ = atan2(B,A) ± acos(C/√(A²+B²))`.
Each in-sector solution emits a straight generator line from base point
(r=N+1) to top point (r=N) — exact under orthographic projection.

**Drawn ops:** base-circle arc, top-circle arc (skipped for `con0`), the
generator silhouette lines (own-occluder excluded, like cylinders).

### 2. Analytic ndis (`primitives.py` + `shade.py`)

`parse_primitive` learns `ndis` (kind `"ndis"`, no numeric). Region, in the
local XZ plane at y=0: inside the unit square (`max(|x|,|z|) ≤ 1`), outside
the unit disc, angle within sector.

- **`NdisOccluder`**: plane hit like `DiscOccluder`, then the region test.
- **Face polygon**: arc polyline (θ: 0→sector, r=1) plus the square boundary
  walked back (point at angle θ is `(cosθ,sinθ)/max(|cosθ|,|sinθ|)`, inserting
  exact corners). Full sector → square exterior ring + circular hole
  (face carries `holes`; see §4). Flat tone via the plane normal, like disc.
- **No drawn ops** — ndis contributes no edges (adjacent `edge` primitives own
  those).

### 3. Cone wall faces + gradients (`shade.py`)

`faces_from_analytic` gains `con`: same near-half/interior-far-half split as
cylinders (`_arc_sector_spans` reused), wall span polygon = top arc (r=N) +
bottom arc (r=N+1) reversed, per-θ gradient samples using the cone normal
`m(θ)` mapped to world via `Minv.T` and normalized (interior spans negated).
`_wall_span_face`/`_radius_pts` are generalized to take per-level radius; the
cylinder call sites keep radii (1, 1) and must produce identical output.
`hlr._visible_segments_analytic` wires `ConeOccluder`/`NdisOccluder` into the
occluder set, own-occluder map, and the fit point cloud (cone: base+top rings;
ndis: square corners + arc).

### 4. Visible-fragment clipping + group merge (`shade.py` / `trace.py`)

`_attach_smooth_gradients` already union-finds faces into groups (seam-joined
smooth groups and coplanar flat groups); it now stamps `f["group"] = <root id>`
on every face. Flat groups keep flat tones; their merge key is the group id.

`fill_ops(faces, style)` becomes:

1. Sort by stamped witness order (unchanged).
2. **Clip**: iterate nearest→farthest, `frag = to_geom(f) − cover`;
   `cover ∪= to_geom(f)`. Drop fragments with area < ~0.2 px². Result:
   pairwise-disjoint visible fragments. Skip the difference when bboxes don't
   intersect (fast path).
3. **Merge**: `union_all` the fragments sharing a group id (they share one
   gradient or one tone by construction). Ungrouped faces pass through.
4. Emit one op per merged fragment, farthest-first (keeps today's
   stroke-overlap aesthetics): `{"d": path_d(geom), fill|gradient, depth}`.

`trace.segments_to_svg` adds `fill-rule="evenodd"` to fill paths (holes from
difference/ndis) and keeps the 0.8 px same-paint stroke — with disjoint
fragments that stroke is what continues to hide antialiasing seams. Gradient
def dedup unchanged. `apply_affine_faces` learns to remap optional `holes`.

Consequences: zero hidden geometry in the SVG; 3960's dish top becomes ONE
gradient path (T-junctions and silhouette self-overlap are non-issues under
union); coplanar flat tessellations (brick tops around studs) merge to one
path per surface; total element count drops sharply.

### 5. Error handling & performance

- Any GEOS failure (invalid ring, topology exception) degrades to the
  unclipped/unmerged polygon for that face — never a crashed render.
- `set_precision` snapping bounds vertex growth; incremental cover union is
  O(n·cost(union)) — acceptable at specimen scale; 3649 (40-tooth gear, the
  face-count stress case) is the benchmark. If it's slow, batch: union chunks
  of ~64 face polys before differencing.
- Areas/thresholds are in output-canvas px (post-affine), so they're
  resolution-honest.

## Testing (TDD; pure-geometry tests run without vendor/)

- `parse_primitive`: `4-4con4`, `1-4con0`, `1-16con13`, `4-4ndis`, `1-4ndis`;
  `tndis`/`cyls`/`chrd` still `None`.
- `ConeOccluder`: axis-aligned analytic hit depths; height/sector clamping;
  `depth_far`; a sheared/scaled transform round-trip.
- Cone silhouette: expected generator angles for a tilted cone; zero
  generators when viewed down-axis (`|C| > √(A²+B²)`).
- Cone faces: near+interior spans, gradient sample normals unit and
  camera-facing; cylinder call sites byte-identical output (regression).
- ndis: polygon area ≈ 4−π (full) / 1−π/4 (quarter); occluder region truth
  table; holes representation.
- `geom2d`: T-junction union (two abutting rects subdivided 16-vs-48 style →
  ONE polygon, exact area); self-overlap union; difference with hole →
  evenodd `d` with two subpaths; degenerate sliver doesn't raise.
- Fragment clipping: fully-hidden face dropped; partial overlap conserves
  total visible area (== union of silhouettes); disjointness of outputs.
- Merge: a seam-grouped facet fan → one op; op-count assertions.
- Integration (skipped without vendor/): 4589 body has no tri facet cloud
  (few analytic gradient fills); 3960 dish = one gradient path; 3941/3001
  render unchanged to the eye; existing sliver/BFC regressions stay green.

## Validation targets

- 3960 dish: single smooth gradient surface, no striping, one path.
- 4589 cone: exact silhouette + smooth wall gradient, analytic.
- Element-count table (before → after) across specimens.txt; expect ~10×
  reduction on curved parts, zero hidden elements everywhere.
- Full specimen render sheet, eyeballed on gray masters.

## Implementation notes (as built, 2026-07-05)

Two deviations from the design above, both found on the validation renders:

- **ndis substitution reverted.** The analytic ndis face gets a flat tone
  (`style.tone`), but in the faceted world its tris join adjacent smooth/
  coplanar facet groups through shared edges and inherit the group's
  GRADIENT — the seam is invisible. Analytic 3960 grew a visible tone-
  mismatched square around its stud (LDView truth: none). Since `fill_ops`'
  union now merges the faceted tris into one region anyway, faceted ndis is
  strictly better: tone continuity AND one element. `parse_primitive`
  documents this; `NdisOccluder` was removed again.
- **Smooth-joint rim arcs suppressed.** Stacked wall sections (4589 =
  `con3` on `con4`) drew a spurious black ring at their shared rim circle.
  Rule (after two refinements): a wall's synthesized base/top arc is skipped
  iff a FULL-sector wall of EQUAL slope lies on the OPPOSITE side of the
  circle plane (`primitives.wall_rims` + `skip_rims`). Same-side sharers,
  creases (unequal slope), and partial-sector sharers keep their arcs —
  3941's base rim is interrupted by cutouts (45°-sector lip walls), remains
  a real edge, and its silhouette tangent lands on it (the historic base-gap
  regression test caught exactly this).

Element counts (paths per SVG, specimens at flat3): 3960 611→33, 3649
2468→416, 4589 221→37, 50950 41→3, 3941 294→86, 3001 105→75. Batch render
time is unchanged (order_faces' witness pass still dominates; booleans are
not a bottleneck at specimen scale).

## Out of scope

- Arc-exact fill outlines (fills remain dense polylines; the arc SVG output
  stays for stroked edges). Possible follow-up: re-fit boolean output to arcs.
- `cyls` (sloped cylinder), `tndis`, tori. Fall back to facets + union merge.
- cel/gradient shading styles; batch library run (later plan tasks).
