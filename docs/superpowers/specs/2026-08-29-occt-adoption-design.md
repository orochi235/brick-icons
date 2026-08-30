# Design: adopting OCCT for hidden-line removal

**Status:** merged to `main` 2026-08-30 (`7543479`), 508 tests passing under
`BRICK_GOLDENS=1`. `--engine occt` ships behind an explicit flag; naive stays
the default and its output is byte-unchanged. Engine work continues on
`occt-port`.

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

`hlr.visible_segments` still computes `out["fit_arcs"]` via `arcfit` before
dispatching to either engine, but `occt.build_shape` reads only
`out["analytic"]` and `out["tri"]` — the fitted arcs are computed and then
discarded on the OCCT path. That is why `32062` loses all 19 of its arcs (see
`## Open`). Feeding those already-computed `fit_arcs` ops into the OCCT
result alongside the kernel's own edges is a cheap follow-up that would
recover them.

The spike's projector frame does not carry over unchanged: it read
`Z = right x up, X = -right`, but empirical enumeration during the port
found the opposite X sign is what matches the naive engine (`Z = right x up,
X = +right`, plus a Y negation) — see `occt.projector_axes`'s docstring for
the authoritative frame and how it was found. The sector-sweep-by-rotation
fix and chiral-feature verification carried over as the spike described them;
the projector frame did not.

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
  as designed. On everything else it stays load-bearing, but the shortfall
  varies by part rather than uniformly zeroing out: the two LDraw dishes
  (`3960`, `4740p03` — spherical-cap BODIES with no matching primitive in
  `occt_faces`) still gain arcs from other recognized features on the same
  part (21→30 and 25→28), `3941`'s hand-faceted rim detail holds flat at 48,
  and only `32062`'s axle (a "+"-profile extrusion, also unmatched) truly
  zeroes — it loses every one of its 19 arcs because its whole body is
  unrecognized triangles. `arcfit` would only retire once `occt_faces` grows
  a dish/sphere and an extruded-profile primitive.
- **`4019`'s stray ellipse is gone**, as predicted, though not for free: bbox
  moves from `[60.77, -11.08, 195.23, 164.0]` (the known arc-recovery
  artifact, against viewBox `0 0 256 170`) to `[60.77, 6.0, 195.23, 164.0]` —
  the same top margin every well-behaved part gets — but its own arc count
  falls too, 74→64. The win on the stray is real; it is not an unqualified
  win on this part.

New findings the spike didn't cover:

**The facet explosion this section measured is fixed, and its stated cause was
wrong.** The numbers here — `L` rising at least 3x on 9 of 23 parts, `4740p03`
2→13359 — were measured while `build_shape` sewed one face per triangle and
drew whatever HLR called sharp, so every tessellation boundary became a crease.
It was read as `UnifySameDomain` declining to merge coplanar facets, and the
proposed fixes were a broader primitive set or a facet-collapse pass. Neither
was needed: LDraw states its edges rather than implying them, so the faces now
serve as occluders only and the drawn candidates are the authored edges alone.
An unauthored boundary is not a candidate to be filtered — it is never a
candidate. Cylinder seam edges were correctly ruled out as minor (~5 of 254
added lines on `3941`); that half stands.

Every per-part figure below and in `task-7-report.md` therefore predates two
rounds of change and should not be planned against. `scripts/compare-engines.py`
re-derives the current table across the `outline` corpus in ~10 minutes.

`6589`'s missing bore geometry is **fixed**; the diagnosis above it in
task-7-report.md (a `ring` annulus papering over the non-circular cutout) was
wrong, and so was "the geometry was never built" — it was built and correctly
hidden. Two independent defects, both silent:

- **`occt_faces` built cylinders and cones as capped solids.**
  `BRepPrimAPI_MakeCylinder(...).Shape()` is a solid; LDraw's `cyli` and `con`
  are open lateral surfaces. Each one added two phantom planar caps — 10 of
  them on `6589` — and the r=9 bore cylinder's cap sealed the axle hole, so
  HLR hid the cross behind material the part does not have. `.Face()` on the
  shared `BRepPrimAPI_MakeOneAxis` base is the lateral surface alone.
- **No full-circle `ring` ever produced a face.** `TopoDS_Wire.Reversed()` is
  typed `TopoDS_Shape`, which `BRepBuilderAPI_MakeFace.Add` refuses; the
  `TypeError` went into `occt_faces`'s blanket `except Exception: return []`.
  All four of `6589`'s rings, and every full ring in every part, silently
  contributed no surface. The bounded-sector path never hit this — it builds
  its inner boundary from edges, not a reversed wire.

Both are pinned by area assertions in `tests/test_occt.py`, which separate
"no face", "face without its hole", and "capped solid" from the correct
result; a count or existence check distinguishes none of them.

Corpus effect is small and mixed: `3673` 311→260 and `3649` 2730→2318 lines,
against `3941` 324→340 and `3941p01` 1257→1270. `6589` itself goes 67→257 as
the recovered bore interior arrives tessellated — mechanism #2 above, now
reaching a part that was previously hiding it.

**`6589`'s bbox x-min shift was mostly the metric, not the geometry.**
`goldens.summarize_svg` builds `bbox` from path ENDPOINTS, and an arc's
extreme normally falls between its endpoints — so re-splitting one ellipse
into a different number of arcs moves the reported number without moving any
ink. Measured against the swept curve by `scripts/compare-extents.py`, the
13.93 shift is 1.22 of real ink; `4589`'s 1.54 and `4740p03`'s 4.66 are
artifact in full, at 0.00 and 0.07. `4019`'s 17.08 is real (18.67 swept), so
the stray-ellipse win stands.

What remains on `6589` is 1.22 in the opposite direction to the one assumed:
naive reaches FURTHER out than OCCT on every side, and its y-min of 4.83
overruns the 6.00 frame margin that OCCT sits exactly on. The outer rim
ellipse is the same under both (80.13 x 49.07 naive, 80.10 x 49.05 OCCT); they
differ only in how much of it each draws. Undiagnosed, but small, and pointing
at naive rather than at the port.

**This makes every `bbox` in `tests/goldens/render/` blind to arc sweep**, so
a bbox delta is not on its own evidence that geometry moved. Fixing the
measure re-freezes all of those goldens, which is why it is not done here.
