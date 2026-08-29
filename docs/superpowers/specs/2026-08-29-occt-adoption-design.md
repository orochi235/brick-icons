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
occlusion, but every case carries fills, and `summarize_svg` does not separate
stroke paths from filled ones — gating on it would make this slice answerable
for the fill path too.

Success is not byte-identity, which is why the summary exists: `bbox`,
`viewBox` and the fill palette hold still while `A` rises and `L` falls on
round parts. A round part whose `A` count does not move is the suspicious one.

## Out of scope

No fills, no `shapely` changes, no `unwrap.py` or decal work, and
`part_geometry` untouched. The fill-boolean question is being evaluated
separately against Skia PathOps; this slice must not pre-empt it.

## Open

- **Whether `arcfit` can be skipped on the OCCT path.** Hand-faceted rounds
  are condline-marked triangle chains, not primitives, so the kernel has no
  exact curve to report for them. They may still need refitting.
- **Whether the spike's four corrections are the whole set.** They came from
  four parts. `4019`'s stray ellipse is predicted to disappear with arc
  recovery, but that is a prediction to check, not a promise.
