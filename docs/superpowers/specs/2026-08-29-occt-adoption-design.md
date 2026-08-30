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
refitted. This is the component that makes `arcfit.py` redundant, and it is
the one to look at first if arcs come out wrong.

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
  primitive (`3001`, `3020`, `4589`, `4070`, `87087`, `99781`) arcs rise and
  lines fall as designed. On everything else it stays load-bearing: `3941`'s
  hand-faceted rim detail, the two LDraw dishes (`3960`, `4740p03` — spherical
  caps with no primitive in `occt_faces`), and `32062`'s axle (a "+"-profile
  extrusion, also unmatched) get no analytic curve at all, and `32062` loses
  every one of its 19 arcs because its whole body is unrecognized triangles.
  `arcfit` would only retire once `occt_faces` grows a dish/sphere and an
  extruded-profile primitive.
- **`4019`'s stray ellipse is gone**, as predicted. Frozen baseline bbox is
  `[60.77, -11.08, 195.23, 164.0]` against viewBox `0 0 256 170` (the known
  arc-recovery artifact); under OCCT it is `[60.77, 6.0, 195.23, 164.0]` — the
  same top margin every well-behaved part in the corpus gets.

New finding the spike didn't cover: parts with no matching primitive don't
fail gracefully, they explode. `UnifySameDomain` correctly declines to merge
triangle facets that approximate real curvature (they aren't actually
coplanar), so every facet boundary comes out as a genuine HLR edge — `L` goes
2→13359 on `4740p03` and 2→1898 on `3960`. Cylinder seam edges, the effect
this task set out to quantify, turn out to be real but minor: `3941`
(A held exactly at 48, `L` 70→324) has 5 seam edges across 13 cylinder faces,
upper-bounding their contribution at roughly 5 of the 254 added lines — the
line explosion is facet tessellation, not seams. The naive engine hid this
because its arcfit/fold-arc/dedupe path collapses a hand-faceted dome to a
couple of silhouette lines; OCCT has no equivalent collapse for
unrecognized curvature. Closing this needs either a broader primitive set
(sphere/dish, extruded-profile) or a facet-collapse pass — both out of scope
for this port.
