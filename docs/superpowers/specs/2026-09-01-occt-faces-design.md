# OCCT faces

For whoever implements `occt.visible_segments`' faces. It answers: where do
the fill faces come from, what shape are their boundaries, and how does
anything downstream know which one is in front?

`occt.visible_segments` returns `faces=()`. That one empty field is the whole
reason `--engine occt` cannot be the default: `fill_ops` gets nothing, so
`--shade-style flat3` and `--opacity` silently degrade to strokes and nothing
errors. `OCCT-MIGRATION.md` holds the ordered work this is item 1 of.

## The two facts the approach rests on

Read off `build_shape(out)` with `BRepAdaptor_Surface` / `BRepAdaptor_Curve`
over 3005, 4740, 3941, 3649, 32062, 3040b and 4589:

- Faces are only `Plane`, `Cylinder` and `Cone`. No spheres, tori or BSpline
  patches.
- Edges are only `Line` and `Circle`. No splines.

So every projected boundary is a segment or a conic arc, and every silhouette
curve is a straight generator. Exact outlines are closed-form for the whole
library, not just the easy parts. Re-derive before trusting this if the
primitive set grows.

## Faces come from the sewn shape

One `fill_ops` face per face of `build_shape(out)` — the same shape HLR draws
edges from, so fills and strokes cannot disagree about the geometry. Counts
run 13 (3005) to 846 (3649).

That is one element per surface by topology rather than by heuristic. Planar
faces still carry `fill_ops`' `plane` key, because `ShapeUpgrade_UnifySameDomain`
declines to merge coplanar neighbours often enough to be the measured cause of
the line explosion; the downstream coplanar union catches what it left split.

**The obvious shortcut is meshing each face and unioning its triangles** —
`face_polys` already does the meshing for the silhouette contour. It gives
chord boundaries that arc recovery only partly repairs, on an engine whose
entire point is that it holds the exact surface.

## Boundaries

Each bounding curve projects in closed form: a line to a segment, a circle to
an ellipse arc, through `locus_arc` / `project_circle`. Points are sampled ON
those curves — never off a mesh — and the ellipses join the arc-recovery list
`visible_segments` already builds, so `fill_ops` re-emits boundary runs as true
`A` commands.

Sampling is not a concession on this engine's exactness — `fill_ops` clips and
merges with shapely, which is polygonal. Conics surviving the booleans is the
`skia-pathops` question, settled as adopt-later in
`docs/superpowers/specs/2026-08-29-pathops-evaluation.md`, and it is a change
to `fill_ops` rather than to this producer.

**Flat face:** the projected wires are the region. Outer wire to `poly`, inner
wires to `holes`.

**Cylinder and cone:** the projected region is not the projection of the wires
— the silhouette is a limb generator that is nobody's edge. Solve for the
parameters where the surface normal turns perpendicular to the view direction,
cut the face there, and emit one face per span, bounded by base arc, limb line,
top arc, limb line. An axis pointing at the camera has no limb and the face
projects inside its own end circles.

This is what `primitives._wall_span_face` already does for naive by sampling 40
points across a span. The difference is that the cut lands exactly on the limb
instead of near it.

## Depth and paint order

`occt` builds a `primitives.Projection` and passes `order_faces` an `own_occ`
map, the way `hlr._visible_segments_analytic` does. The occluders are the
existing `CylinderOccluder`, `ConeOccluder`, `DiscOccluder` and
`TriangleOccluder`, constructed from the OCCT surface's axis and radius — they
take `(R, t, sector, …)` and are already exact under elliptical scale.

This pulls `OCCT-MIGRATION.md` item 2 into this slice, deliberately: a curved
face bows toward the camera between its edges, which is exactly where it
overlaps its neighbour, so a flat depth is wrong at the point that decides the
order.

**Open, revisit if it fights back.** If constructing occluders from OCCT
surfaces proves heavy, the fallback is a flat depth per limb-split span —
`_plane_depth_fn` handles it today and no shared code changes. Nothing else in
this design depends on which of the two is in place.

**Trap.** `occt` works in projected LDU with Y negated (`_negate_y`,
`face_polys`' `P[:, 1] *= -1`) and `apply_affine_faces` applies the canvas fit
later. The `Projection` handed to `order_faces` must map world into the space
the polygons are actually in, or `ray_origin` inverts into the wrong place.
The frame was settled by enumeration once already; check it the same way
rather than deriving it.

## Colour and tone

Everything is colour 16. Sewing drops LDraw colour, and printed parts are out
of the engine loop, so decoration colour is item 4's problem. Flat faces carry
a view-space `normal` for the flat3 tone; curved spans carry `grad_axis` and
`grad_samples` built from the exact surface normal, in the field shape
`_wall_span_face` emits.

## Out of scope

`refits`, `loops` and `fold_ells` (item 3); `tri` / `tri_colors` and decal
unwrap (item 4); retiring the silhouette contour (item 5). The contour stays
until fills exist, then gets measured for redundancy rather than assumed dead.

## How it is judged

Parity with naive across the corpus. `scripts/compare-engines.py` renders only
the strokes-only `outline` combo today; it grows a combo argument and runs
`outline-flat3` over the 21 `unprinted` parts, reporting fill palette, element
counts, bbox and raster RMSE for naive against occt.

Unit tests in `tests/test_occt.py`: face counts and kinds per part, a span's
boundary points lying on the true ellipse, hole nesting, limb-split counts, and
occluder depth against the surface it was built from. Mutate each new guard and
watch it go red — five tests on this branch could not fail before review caught
them.

The naive path is untouched, so `tests/goldens/hashes.txt` must not move.

## Landing order

Flat faces first: 32062 is 178 planar faces and no curves at all, 3005 is 12
planes and one cylinder, so fills appear and the plumbing is proven before any
limb solving. Curved spans and gradients second.
