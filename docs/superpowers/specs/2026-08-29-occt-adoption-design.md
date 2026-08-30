# Design: adopting OCCT for hidden-line removal

**Status:** approved 2026-08-29, not yet implemented.

**Reader:** whoever implements or reviews the port. Assumes
`2026-08-29-occt-spike.md` has been read — this spends its words on what to
build, not on whether to.

**Question it answers:** where does the OCCT engine attach, and what tells us
it works?

## The seam

`brick_icons/occt.py` is the only module that imports `OCP`.
`hlr.visible_segments` gains `engine="naive"|"occt"` and dispatches after the
shared front end (`flatten` → `repair`), returning the same `VisResult` from
either path. `config` gains `engine`; the CLI gains `--engine`.

Nothing downstream changes: `fit_segments`, `fit_affine` and
`segments_to_svg` are already engine-agnostic, and the CLI reaches the engine
through `visible_segments` and `part_geometry` alone.

A protocol with `engines/naive.py` and `engines/occt.py` is the honest
end-state, and it is deliberately not built yet. Extracting it now would
relocate most of a 54KB file before we know the OCCT path is right, and would
guess at an interface that has one real implementation. It becomes worth doing
when `--engine occt` is the default and the naive engine is deleted.

## Components

**`build_shape(out)`** — recognized primitives become real geometry (`cyli` →
`MakeCylinder`, `disc`/`ring` → annular face, `con` → cone); leftover
triangles become planar faces. Then `Sewing` → `UnifySameDomain` →
`ShapeFix_Shape`. The 5% of primitives with sheared frames fall back to their
triangles.

**`hlr_edges(shape, right, up, fwd, cull)`** — `HLRBRep_Algo`, reading
`VCompound` / `Rg1LineVCompound` / `OutLineVCompound`. With `cull=False` the
`H*` variants supply hidden edges, so the `--wireframe` and `--opacity`
draw-everything path is served by the same code rather than by a second one.

**`edges_to_ops(edges)`** — lines pass through; `Geom_Circle` and
`Geom_Ellipse` are read off the curve into our ellipse records. Nothing is
refitted. On a recognized primitive this makes `arcfit.py`'s own refitting
redundant — measured in `## Open` below, `arcfit` still runs and still
matters for hand-faceted geometry `occt_faces` never recognizes. This
component is the one to look at first if a recognized primitive's arcs come
out wrong.

Three corrections from the spike are implementation contract rather than
background — the projector frame, sector sweep by x-direction rotation, and
verifying orientation against a chiral feature. The spike's Findings section
carries the detail and the evidence.

## A failed part raises

`--engine occt` never falls back to the naive engine. A silent fallback would
let the gate report success for parts the kernel never touched — the same
class of defect as goldens that cannot move. Missing `OCP` raises at module
import with a message naming `pip install -e '.[occt]'`.

`cadquery-ocp` is an optional extra, not a dependency. It is 935MB installed,
592MB of which is a transitive VTK the port never calls, and the repo installs
with a plain `pip install -e .`.

## The gate

A plain `outline` combo — occlusion on, strokes only, no `--shade-style` —
frozen from the naive engine and added to `tests/goldens/manifest.toml`.

The frozen combos cannot serve. `--wireframe` sets `cull=False` (`cli.py`,
"translucent or wireframe: draw hidden geometry too"): on `3001` it draws 46
paths against plain outline's 26, the extra 20 being what occlusion removes,
so it cannot gate hidden-line removal. `outline-flat3` does exercise
occlusion, but its `commands` counts aggregate across every path: turning
fills on takes `3001` from `A` 58 to 192 and `L` 32 to 273. The arc/line split
is exactly the signal that reads as kernel intent, so fills drown it. (The
`fills` field itself stays separable — it is `commands` that mixes.)

Success is not byte-identity, which is why the summary exists: `bbox`,
`viewBox` and the fill palette hold still while `A` rises and `L` falls on
round parts. A round part whose `A` count does not move is the suspicious one.

## Out of scope

No fills, no `shapely` changes, no `unwrap.py` or decal work, and
`part_geometry` untouched. The fill-boolean question is being evaluated
separately against Skia PathOps; this slice must not pre-empt it.

## Open

Task 7 ran `scripts/compare-engines.py` over all 23 `outline` cases
(`.superpowers/sdd/2026-08-29-occt-hlr-port/task-7-report.md` has the full
table). Both predictions above are now measured, not open:

- **`arcfit` is not removable.** On parts whose geometry matches a recognized
  primitive (`3001`, `3020`, `4589`, `4070`, `87087`) arcs rise and lines fall
  as designed. On everything else it stays load-bearing: `3941`'s hand-faceted
  rim detail, the two LDraw dishes (`3960`, `4740p03` — spherical caps with no
  primitive in `occt_faces`), and `32062`'s axle (a "+"-profile extrusion,
  also unmatched) get no analytic curve at all, and `32062` loses every one of
  its 19 arcs because its whole body is unrecognized triangles. `arcfit`
  would only retire once `occt_faces` grows a dish/sphere and an
  extruded-profile primitive.
- **`4019`'s stray ellipse is gone**, as predicted, though not for free: bbox
  moves from `[60.77, -11.08, 195.23, 164.0]` (the known arc-recovery
  artifact, against viewBox `0 0 256 170`) to `[60.77, 6.0, 195.23, 164.0]` —
  the same top margin every well-behaved part gets — but its own arc count
  falls too, 74→64. The win on the stray is real; it is not an unqualified
  win on this part.

New findings the spike didn't cover:

Parts with no matching primitive don't fail gracefully, they explode — and
this is 9 of the 23 parts, not a couple: `L` rises at least 3x on `4740p03`
(2→13359, x6680), `3960` (2→1898, x949), `3941p01` (74→1257, x17),
`3040bp08` (38→485, x12.8), `3941` (70→324, x4.6), `6143` (59→228, x3.9),
`3673` (90→311, x3.5), `32062` (140→440, x3.1) and `3649` (917→2730, x3.0).
All nine share one mechanism: `UnifySameDomain` correctly declines to merge
triangle facets that approximate real curvature or fine tessellated detail
(they aren't actually coplanar, or don't fully reduce even when they are —
merge rates measured directly range from 1.5% on `4740p03`'s dome to 83% on
`3040bp08`'s print), so every surviving facet boundary comes out as a genuine
HLR edge that the naive engine's arcfit/fold-arc/dedupe path used to collapse
to a handful of silhouette lines. OCCT has no equivalent collapse for
unrecognized curvature. Cylinder seam edges, the effect this task originally
set out to quantify, turn out to be real but minor by comparison: `3941`
(`A` held exactly at 48, `L` 70→324) has 5 seam edges across 13 cylinder
faces, upper-bounding their contribution at roughly 5 of the 254 added lines
— the explosion is facet tessellation, not seams. Closing this needs either
a broader primitive set (sphere/dish, extruded-profile) or a facet-collapse
pass — both out of scope for this port.

`6589` (Technic Gear 12 Tooth Bevel) loses geometry outright, not just arcs:
bbox x-min moves from 61.34 to 75.27, and the naive render's cross-shaped
axle-hole notch inside the bore is entirely absent from the OCCT render —
confirmed not an occlusion artifact (`hlr.visible_segments(..., cull=False)`
reports the identical bbox extremes as `cull=True`, so the missing ink isn't
hidden geometry becoming visible, it was never built). The likely cause:
`occt_faces` recognizes a `ring` primitive for the bore's flat web as a
perfect annulus, which cannot represent the true non-circular cutout — the
same "no primitive for a non-circular hole" gap as `32062`'s axle profile,
here manifesting as lost material instead of lost arcs. `4740p03`'s smaller
4.66 bbox shift, by contrast, looks like ordinary facet-vs-analytic silhouette
noise on the dome, not missing geometry — not confirmed further.
