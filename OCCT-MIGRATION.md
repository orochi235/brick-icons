# Migrating the renderer to `--engine occt`

For whoever picks the port back up. It answers one question: **what has to
exist before `occt` can be the default engine**, and what is out of scope.
Per-part defects live in `HANDOFF.md`; where the engine attaches and what
gates it lives in `docs/superpowers/specs/2026-08-29-occt-adoption-design.md`.

Today `naive` is the default and its output is byte-locked by
`tests/goldens/hashes.txt`. `occt` runs behind the flag and raises rather than
falling back, so a part it cannot draw fails loudly.

## Scope: two flags, not the whole CLI

`cli.process_one` returns to the LDView raster path before any engine call
unless `--shading outline` or `--wireframe` is set. So `--shading normal`,
`cel` and `color` are not part of this migration and cannot gate it.

Decal extraction is not part of it either: `hlr.part_geometry` is a flatten
plus `repair.repaired_tris`, with no projection, z-buffer or occlusion pass —
it never reaches an engine, and `brick-icons decal` takes no `--engine`.

## Faces, and what they carry

`occt.visible_segments` returns fill faces: one per planar face of the sewn
shape, and one per limb-cut span of each cylinder, cone and elliptical wall.
`--shade-style flat3` and `--opacity` work under `occt`.

**What a face has to carry.** `fill_ops` reads `poly` (canvas-space `(N,2)`),
`normal` (view space), `depth`, `zs`, `plane`, `color`, `group`, `holes` and
`prim`, plus the gradient fields a curved surface needs (`grad_axis`,
`grad_radial`, `grad_samples`). `shade.faces_from_tris` and
`faces_from_analytic` are the two existing producers -- read them as the
contract, and `occt._faces_for` as the third.

What is still empty under `occt`: `refits`, `loops` and `fold_ells` (item 3),
`tri` and `tri_colors` (item 4). Every face is color 16, because sewing drops
LDraw color.

**A surface kind the producer does not handle contributes no fill and raises
nothing.** That is how 50950's elliptical wall stayed empty. `CURVED_SURFACES`
plus `Plane` is the handled set, and
`test_every_corpus_surface_kind_is_one_the_face_producer_handles` fails when
the corpus grows one the producer does not know.

## Ordered work

1. **Faces. DONE.**
2. **`proj`. DONE**, with item 1 rather than after it: a curved face bows
   toward the camera between its edges, which is exactly where it overlaps a
   neighbour, so a flat depth is wrong at the point that decides the order.
3. **Decoration.** Five separate gaps, all in the table below; the first one
   is the size of the whole printed corpus. Nothing here is optional before
   `occt` can draw a printed part.
4. **Decide about the naive stylizations.** `refits`, `loops` and `fold_ells`
   are empty under `occt`. Either port them or establish that exact faces make
   them unnecessary — do not port them on the assumption that they are needed.
5. **Retire the silhouette contour.** It exists because `occt` has no faces;
   check whether real faces make it redundant before leaving it in.

## What naive does that occt does not

Read the two pipelines against each other — `hlr._visible_segments_analytic`
plus the tail of `hlr.visible_segments`, against `occt.visible_segments` and
`occt.ordered_faces`. The `occt` branch returns before naive's whole
post-processing tail, and its face path reaches `shade` through a narrower
door.

### Decoration

| naive does | occt does | |
|---|---|---|
| `faces_from_analytic` keeps `prim.color`, so a substituted disc or cone that is *print* paints as print | `build_shape` sews every face and stamps it `color: 16`; `_with_decoration` re-reads colors from `out["tri_colors"]` only | **absent.** 4,553 of 13,083 printed parts author some decoration as an analytic primitive, and 202 author *all* of it that way. `3942bp01`'s cone stripes are 16 color-4 `con` prims and no colored triangle at all, so occt draws a bare gray cone; `3040bp08` keeps its yellow border (triangles) and loses its three yellow discs (`disc` prims) |
| `unwrap_decoration(carriers=analytic)` — a decal binds to the cylinder or cone it is printed on | `carriers=[]` — a decal can only bind to a plane OCCT happened to build | **absent** |
| `unwrap_decoration(ellipses_out=decal_ells)` — a flat decal's circular boundary runs come back as arcs instead of the author's chords | `ellipses_out` not passed, so `_decal_arc_candidates` never runs | **absent, and the machinery already works.** Threading the list through recovers 3 candidates on `003428d` and 108 on `004490h` from the planes OCCT has already built |
| `ink_prims` — a print's boundary is ink, not a crease, so its primitive does not stroke | no analog; `authored_loci` takes every `edge` primitive | **absent, latent.** The primitives it suppresses are ones occt today neither colors nor strokes, so it does not yet show; it becomes load-bearing the moment the two rows above land |
| `res.tri` / `res.tri_colors` reach `cli._emit_unwrap` | `()` | **absent.** `--debug-dir` writes no `.unwrap.svg` under `occt` — the one view that shows whether a carrier bound correctly, missing on the engine the decal work is being done on |

### Stroke post-processing

The `occt` branch of `hlr.visible_segments` runs `fit_silhouette_arcs` and
`cull_orphan_runs` and returns. Everything else in that tail is naive-only.

| naive does | occt does | |
|---|---|---|
| `dedupe_segments` unions abutting and overlapping spans on one carrier line or ellipse | not called | **absent.** `4740` emits 18 ops where 9 suffice — its outer rim arrives as `225→360` and `180→225`, drawn as two strokes meeting at a seam that composites its antialiasing twice. Also `3001` 71→47, `3941` 104→77, `2654a` 168→122. Not a one-line call: `eps=0.05` is canvas px on naive and projected LDU on occt, so it has to scale by `res.s` |
| `_snap_rim_crossings` pass 1 snaps a partial arc's ends onto the junction they graze | not called | **absent.** `max_snap` is degrees and scale-free; `vertex_tol=0.25` is op units and needs the same scaling |
| `_snap_rim_crossings` pass 2 refits a counterbore separator, and `fill_ops(refits=)` moves the fill seam to follow it | `refits=()`, so `refit_fill_boundaries` never fires | **absent** |
| `_refit_candidates(refits)` makes the moved seam an arc candidate | — | **absent**, follows the row above |
| `_fold_arc_loops` turns chained fold-arc spans into `fill_ops(loops=)` sub-region outlines | `loops=()` | **absent.** `fold_ells` is built from `fit_ells` inside `_visible_segments_analytic`, which occt never enters |
| `cull_orphan_runs(protect=fold_ells)` | called with no `protect` | present but unprotected; vacuous while `fold_ells` is empty, wrong the moment it is not |

### Present under another mechanism — do not port

| naive | occt |
|---|---|
| `visible_subops` sampled occlusion against analytic occluders | real hidden-line removal (`hlr_edges`) |
| `smooth_rim_skips` per-angular-bin seam suppression | `UnifySameDomain` plus `analytic_creases`'s `TANGENT_DEG` |
| `faces_from_analytic` | `_faces_for` / `curved_faces` |
| `fit_arcs` drawn as arcs, occluded along a chord proxy | `authored_loci` matches the authored chords and `locus_arc` re-reads them against the arc |
| `absorb_wall_facets` | not applicable: occt's walls are OCCT surfaces, and an authored color-16 wall quad never becomes an occt face |
| rim arc candidates carry a 25° max step so a 16-gon's chords are recognized | occt samples its own boundaries at `BOUNDARY_STEP_DEG` 9°, under `geom2d.MAX_STEP` 15°, so they recover without help. The coarser step still matters for the faces occt derives from triangles |

### occt-only, with no naive analog

`_undeclared_ops` (1,407 stickers declare no edge and naive draws them blank),
`_pierce_seams`, `_group_planes`, `_boundary_conics`, and the `sil_polys`
silhouette contour.

## The gate that has to exist first

`tests/test_occt.py` is the entirety of `occt`'s coverage. `hashes.txt` locks
whatever engine froze it, so it is a drift lock on `naive` and nothing else.

Cases in `tests/goldens/manifest.toml` are data, so an `occt` combo is a row
carrying `--engine occt`, not a harness change — that gives `occt` its own
drift lock. What it cannot give you is cross-engine equality: a BRep kernel
reads a circle where `naive` refits a polyline onto a guessed arc, so a
*correct* engine misses every naive hash by construction.
`scripts/compare-goldens.py` exists for that reason — it ignores hashes and
diffs the raster and the structural summary.

## Traps specific to the two engines coexisting

- **The two engines emit ops in different spaces.** `naive` works in canvas px
  at `render_px`; `occt` returns projected LDU and lets `fit_segments`
  normalize. This is what makes porting the post-processing tail more than a
  call: `dedupe_segments`'s `eps=0.05` and `_snap_rim_crossings`'s
  `vertex_tol=0.25` are canvas px and mean something else in LDU.
  `cull_orphan_runs` already runs on both because it derives its thresholds
  from the ops bbox, and `_snap_rim_crossings`'s `max_snap` is in degrees.
- **`arcfit` MOVES its chains out of `out["2"]`.** Anything reading authored
  type-2 edges must also read `out["fit_arcs"]`; `occt.authored_loci` did not,
  and every axle hole, gear hub and notch pocket was undrawable — silently,
  because a locus that matches nothing raises nothing.
- **`occt_faces` catches every exception and returns `[]`.** Two defects lost
  whole surfaces for the life of the port with no error anywhere. Remove the
  `except` and look before believing a `[]`.
- **Arc parameters are degrees** across this codebase; OCCT reports radians.
