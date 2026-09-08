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
3. **Decoration. DONE** (`175bc8f`), except `ink_prims`, which was tried and
   is wrong here — see the table.
4. **Decide about the naive stylizations.** `refits`, `loops` and `fold_ells`
   are still empty under `occt`. Either port them or establish that exact
   faces make them unnecessary — do not port them on the assumption that they
   are needed. `dedupe_segments` was the one stage of that tail that clearly
   belonged, and it landed in `b4b3c62`.
5. **Retire the silhouette contour.** It exists because `occt` has no faces;
   check whether real faces make it redundant before leaving it in.

## What naive does that occt does not

Read the two pipelines against each other — `hlr._visible_segments_analytic`
plus the tail of `hlr.visible_segments`, against `occt.visible_segments` and
`occt.ordered_faces`.

**Four of these are closed** (`175bc8f`, `b4b3c62`). Two were tried and are
wrong for this engine, and the rows say why so nobody re-proposes them. The
rest of the tail is still open and is item 4 above.

### Decoration

| naive does | occt does | |
|---|---|---|
| `faces_from_analytic` keeps `prim.color`, so a substituted disc or cone that is *print* paints as print | `build_shape` sews every face and stamps it `color: 16`; `_with_decoration` re-reads colors from `out["tri_colors"]` only | **CLOSED, `175bc8f`** — the faces are built from the primitive list instead, with their own occluders. 4,553 of 13,083 printed parts author some decoration as an analytic primitive, and 202 author *all* of it that way. `3942bp01`'s cone stripes are 16 color-4 `con` prims and no colored triangle at all, so occt draws a bare gray cone; `3040bp08` keeps its yellow border (triangles) and loses its three yellow discs (`disc` prims) |
| `unwrap_decoration(carriers=analytic)` — a decal binds to the cylinder or cone it is printed on | `carriers=[]` — a decal can only bind to a plane OCCT happened to build | **CLOSED, `175bc8f`** |
| `unwrap_decoration(ellipses_out=decal_ells)` — a flat decal's circular boundary runs come back as arcs instead of the author's chords | `ellipses_out` not passed, so `_decal_arc_candidates` never runs | **CLOSED, `175bc8f`.** 3 candidates recovered on `003428d`, 108 on `004490h` |
| `ink_prims` — a print's boundary is ink, not a crease, so its primitive does not stroke | no analog; `authored_loci` takes every `edge` primitive | **TRIED AND WRONG.** Its first rule is "color is not 16", and a printed part whose *body* is authored in a color — `9359` is a green brick with a white TAXI print — has every structural edge it owns caught by it. Porting it took the stud rims off `9359`, `80400` and `6141p01`. Naive needs the rule because a substituted primitive there draws its own rim; nothing on this side draws one |
| `res.tri` / `res.tri_colors` reach `cli._emit_unwrap` | `()` | **CLOSED, `175bc8f`.** `--debug-dir` now writes the `.unwrap.svg` under `occt` |

### Stroke post-processing

The `occt` branch of `hlr.visible_segments` runs `fit_silhouette_arcs` and
`cull_orphan_runs` and returns. Everything else in that tail is naive-only.

| naive does | occt does | |
|---|---|---|
| `dedupe_segments` unions abutting and overlapping spans on one carrier line or ellipse | not called | **CLOSED, `b4b3c62`.** 2,202 drawn ops to 1,692 over 36 parts. It takes `eps=0.05/res.s` because occt works in LDU, and a new occt-only `keep_order` that stops the pass regrouping the list and rebuilding ops it did not merge |
| `_snap_rim_crossings` pass 1 snaps a partial arc's ends onto the junction they graze | not called | **CLOSED as WRONG, do not port** -- see below |
| `_snap_rim_crossings` pass 2 refits a counterbore separator, and `fill_ops(refits=)` moves the fill seam to follow it | `refits=()`, so `refit_fill_boundaries` never fires | **absent** |
| `_refit_candidates(refits)` makes the moved seam an arc candidate | — | **absent**, follows the row above |
| `_fold_arc_loops` turns chained fold-arc spans into `fill_ops(loops=)` sub-region outlines | `loops=()` | **absent.** `fold_ells` is built from `fit_ells` inside `_visible_segments_analytic`, which occt never enters |
| `cull_orphan_runs(protect=fold_ells)` | called with no `protect` | present but unprotected; vacuous while `fold_ells` is empty, wrong the moment it is not |

#### The snap passes on occt: pass 1 deletes edges, pass 2 draws the strays

`scripts/snap-render-ab.py` splices in `_snap_rim_crossings`, which runs BOTH
passes -- so its rendered A/B measures the pair, and the first reading of it
here blamed pass 1 for what pass 2 does. What separates them is that pass 1
moves an endpoint by at most `max_snap` = 4 degrees, so a span can change by 8;
measured over the eight parts below it never changed one by more, and it cannot
turn a short arc into a long one.

**Pass 1 drops a drawn element on one occt part in nine, and visible ink on
one in eighteen.** It exists for naive's SAMPLED occlusion: `visible_subops(n=64)` stops up to a sample short of
the true graze, leaving an arc end beside the stroke it should touch. occt does
real hidden-line removal and lands it, so there is nothing for the pass to
repair -- but it still fires, and where it fires it can drop an element rather
than move one.

**Count the SVG's elements, off against on** -- `scripts/snap-element-delta.py`.
Over the 148 A/B parts with zero pass-2 refits, so pass 1 is the only thing
running, 16 come out with fewer `<path>` plus `<line>` elements than they went
in with:

    part        elements   largest diff component
    30124b          -10    1,998 px
    33089            -7      823 px
    76421            -7      480 px
    67887            -4      928 px
    11264            -4      318 px
    24130            -3    2,053 px
    18970            -3      254 px
    48812            -2    1,916 px
    3648a            -2    1,288 px
    3896             -2      944 px
    43368            -1      115 px
    87616            -1        5 px
    93087k01         -1       68 px
    99930            -1    1,211 px
    5405             -1    1,229 px
    7335             -1       89 px

Eight lose an edge you cannot miss -- `24130`, `33089`, `48812`, `30124b`,
`5405`, `99930`, `76421` each lose a long stroke, and `67887` loses a closed
panel outline. `24130`'s is the clearest: its foot ring's whole front arc,
three arcs and about 230px of edge, replaced by a 16px `<line>` stub.
**`67887` and `33089` were previously recorded here as "identical to the eye";
they are not** -- an eyeball pass over a full-frame render is not sensitive
enough for this, and the element count is, at no cost.

So pass 1 on occt is inert at best and destructive at worst, and never a
repair.

**Pass 2's separator refit is what draws the stray arcs**, and the mechanism is
its sweep direction, not its size. Radii barely move (0.6-1.2x of the arc being
replaced), but every refit lands at a span of 238-343 degrees whatever it
started from:

    part      old r   new r   old span   new span   growth
    23801     20.15   13.69       41.7      288.7      6.9
    23801      6.75    6.93       45.0      335.1      7.4
    35c01     35.47   21.97      180.0      339.8      1.9
    18585      6.45    5.55      119.9      281.6      2.3

That is the short-arc-as-its-long-complement failure `test_goldens.py`'s
KNOWN_STRAY note records for `4019`: the circumcircle through (pinch1, pinch2,
M's apex) is emitted the long way round instead of through the apex.

**`SEP_REFIT_MAX_GROWTH` cannot be tuned out of it.** At 10.0 it passes all of
these, but growth does not separate the damaged parts from the clean ones --
`32291` is visibly wrong at 2.6x while `18585` is clean at 2.3x. The fix is to
pick the sweep that keeps the apex BETWEEN the pinch points, which is what the
refit means; a threshold only hides how often it picks the other one.

So neither row is worth porting as it stands. Pass 1 is machinery with no
defect to fix, and pass 2 is stylization -- making a separator read concentric
with its bore -- carrying a live direction bug. Fix the sweep before anyone
argues about whether the stylization is wanted.

### Present under another mechanism — do not port

| naive | occt |
|---|---|
| `visible_subops` sampled occlusion against analytic occluders | real hidden-line removal (`hlr_edges`) |
| `smooth_rim_skips` per-angular-bin seam suppression | `UnifySameDomain` plus `analytic_creases`'s `TANGENT_DEG` |
| `faces_from_analytic` | `_faces_for` / `curved_faces` |
| `fit_arcs` drawn as arcs, occluded along a chord proxy | `authored_loci` matches the authored chords and `locus_arc` re-reads them against the arc |
| `absorb_wall_facets` | not applicable: occt's walls are OCCT surfaces, and an authored color-16 wall quad never becomes an occt face |

### Arc candidates

`geom2d.arc_candidates` reads an optional 7th element as that candidate's max
step in degrees and an 8th as a per-candidate snap tolerance in px. naive sets
both; occt appends bare 6-tuples, so every candidate it emits takes the default
`MAX_STEP` 15° and no tolerance.

| naive does | occt does | |
|---|---|---|
| every drawn circle is a candidate at a 25° max step, because a face authored as an LDraw 16-gon rings a hole in 22.5° chords and cannot recover as an arc under 15° | bare 6-tuples: `MAX_STEP` 15° | **absent.** occt's own surface boundaries sample at `BOUNDARY_STEP_DEG` 9° and do recover unaided, but a triangle is sewn into a planar face whose boundary is still the authored chord polygon. Giving occt's candidates naive's 25°: `32062` 43 arc commands to 75 and 26,360 bytes to 21,573 with the raster unchanged; `3941` 141 to 164, and two kinks in the counterbore band become curves. 4 of 6 faceted specimens move |
| `fit_ells` carries a MEASURED snap tolerance so a fill seam authored along the facet chain snaps onto the DRAWN arc | no tolerance | **absent**, follows the row above |

### The junction-lens layer is not a fill

`test_a_fill_boundary_carries_no_sampled_boundary` reads every filled path and
fails on a run of sub-quarter-pixel segments. A junction-lens pocket
(`shade._ink_lens_pockets`) is a difference against the buffered stroke band,
so its boundary is a buffer boundary *by construction*; it is area-capped,
must vanish under an opening at half a stroke width, and paints black beneath
the ink enclosing it. Counting it measures how gnarly the pockets are, not
whether a surface fill inherited a sampling — which is what cost `32062` a
2→17 reading against a non-black worst run of 1. The gate skips pure black,
which under `flat3` is that layer and nothing else.

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
