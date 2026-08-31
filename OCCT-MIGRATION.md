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

## The blocker: `occt.visible_segments` returns `faces=()`

That single empty field is the whole gap. Everything below follows from it,
and none of it errors — `fill_ops` returns nothing, `trace.segments_to_svg`
emits strokes, and the render comes back looking plausible.

| what silently disappears | why |
|---|---|
| `--shade-style flat3` (the only style in `shade.STYLES`) | `fill_ops` gets an empty face list |
| `--opacity` below 1 | translucency is painted fills; the unculled strokes still draw |
| `shade.silhouette_spur_trim` | guarded by `if faces` |
| witness-order paint sort | `shade.order_faces` has nothing to order |

`cli._sil_faces` substitutes `res.sil_polys` so the silhouette contour still
draws, which is why the hole was invisible for the life of the port.

**What a face has to carry.** `fill_ops` reads `poly` (canvas-space `(N,2)`),
`normal` (view space), `depth`, `zs`, `plane`, `color`, `group`, `holes` and
`prim`, plus the gradient fields a curved surface needs (`grad_axis`,
`grad_radial`, `grad_samples`). `shade.faces_from_tris` and
`faces_from_analytic` are the two existing producers — read them as the
contract. OCCT already holds these surfaces exactly; the work is projecting
each to a polygon with holes and carrying the grouping metadata, not
recovering geometry.

## Ordered work

1. **Faces.** Project the sewn shape's faces to `fill_ops`'s contract. Done
   when `--shading outline --shade-style flat3` fills under `occt`.
2. **`proj`.** `occt` returns `proj=None`. `order_faces` and
   `_face_depth_probe` use it to probe a face's own occluder along the witness
   ray, which is what makes the depth exact on a CURVED surface; without it
   both fall back to the face's affine screen-depth plane.
3. **Decide about the naive stylizations.** `refits` (the counterbore
   separator refit), `loops` and `fold_ells` (fold-arc sub-region outlines) are
   all empty under `occt`. Either port them or establish that exact faces make
   them unnecessary — do not port them on the assumption that they are needed.
4. **`tri` / `tri_colors`.** Empty under `occt`, which turns off
   `--debug-dir`'s unwrap emission (`cli._emit_unwrap`) and
   `shade.unwrap_decoration`, so bound decoration never reaches the render
   path. Needed before printed parts can gate anything but `outline-flat3`.
5. **Retire the silhouette contour.** It exists because `occt` has no faces;
   check whether real faces make it redundant before leaving it in.

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
  normalize. Harmless until post-processing is shared: `dedupe_segments`
  (`eps=0.05`), `_snap_rim_crossings` (`max_snap=4.0`) and `cull_orphan_runs`
  are px-scale constants and run only on the `naive` branch.
- **`arcfit` MOVES its chains out of `out["2"]`.** Anything reading authored
  type-2 edges must also read `out["fit_arcs"]`; `occt.authored_loci` did not,
  and every axle hole, gear hub and notch pocket was undrawable — silently,
  because a locus that matches nothing raises nothing.
- **`occt_faces` catches every exception and returns `[]`.** Two defects lost
  whole surfaces for the life of the port with no error anywhere. Remove the
  `except` and look before believing a `[]`.
- **Arc parameters are degrees** across this codebase; OCCT reports radians.
