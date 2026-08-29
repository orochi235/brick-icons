# Spike: replace the hand-rolled geometry with OCCT

**Status:** probe complete, 2026-08-29. **Verdict: go for the HLR track; the boolean track is unproven.** Findings at the bottom.

**Question:** can an exact BRep kernel take over everything downstream of
primitive recognition — occlusion, arc recovery, seam dedupe, fill booleans —
and make the open bugs in `HANDOFF.md` structurally impossible rather than
individually fixable?

**Reader:** whoever picks up the go/no-go. Assumes the current pipeline is
already understood; spends its words on OCCT specifics instead.

## What we'd install

`pip install cadquery-ocp` — the pybind11 binding (OCP) that CadQuery and
build123d run on, wrapping OCCT 7.9.3. PyPI carries a `cp314` /
`macosx_11_0_arm64` wheel, so it drops into this `.venv` on Python 3.14,
native arm64, no conda and no Rosetta. Linux `aarch64`/`x86_64` and Windows
wheels are there too, so the README's porting note stays true.

Not pythonocc-core: the older SWIG binding, conda-forge only in practice, and
it would force this repo off plain `pip install -e .`.

## Why — the failure classes

Every open bug in the handoff is a consequence of representing curved
surfaces two ways at once — an exact circle for the analytic occluder, a
chord polygon for the drawn facets — and then reconciling them numerically. A
BRep kernel holds one representation with shared topology, so the
reconciliation step does not exist.

| today | OCCT | what stops being a problem |
|---|---|---|
| `hlr.py` z-buffer + per-primitive analytic depth field + `clip_visible` | `HLRBRep_Algo` → `HLRBRep_HLRToShape` (`VCompound`, `Rg1LineVCompound`, `OutLineVCompound`) | Hidden-line removal is exact and reports sharp / smooth / silhouette edges separately — the `--silhouette-width` distinction is kernel output, not inference |
| `primitives.py`'s `depth()` / `depth_far()` occluders | — deleted | Occlusion is the kernel's; the recognizer only has to *build* the shape |
| `arcfit.py`, `_refit_candidates`, `_fold_arc_loops` (arc recovery) | — deleted | HLR emits edges whose curves already are `Geom_Circle` / `Geom_Ellipse`. Read the curve off the edge instead of refitting a polyline onto a guessed one |
| `rim_key`, `canonical_rim_keys`, `dedupe_segments` | `BRepBuilderAPI_Sewing` + `ShapeUpgrade_UnifySameDomain` | A rim shared by two subparts is one edge after sewing — the redraw problem is gone before HLR runs, not unioned away after |
| the ragged bore (`cyli r=4` wall vs 56-chord floor) | `BRepAlgoAPI_Cut` | Wall and floor meet on one exact circular edge. `facet_snap_rims` and the "fills snap but drawn chords don't" trap both evaporate |
| shapely 2D fill booleans; `TopologyException` on `4740p03` | `BRepAlgoAPI_Common` / `_Cut` on projected planar faces | Booleans that preserve arcs, so fills and strokes are exact by one construction instead of by two heuristics agreeing |
| `unwrap.py` carrier binding by fitting | `BRepAdaptor_Surface.GetType()`, `ShapeAnalysis_Surface.ValueOfUV` | The carrier is stated by the face, not fitted from facets; UV is the surface's own parameterization, so the bespoke cylinder/cone unwrap math goes |

Two things it does not fix. **Organic bodies still have no single carrier** —
a Friends leg is genuinely a thousand facets, and OCCT gives the same honest
per-face answer the proof sheet already gives. **`--opacity`'s far-to-near
draw-everything path** is not an HLR problem, so it keeps its own code path.

## The crux

LDraw is triangle soup plus primitive references: no topology, no
watertightness guarantee. The spike turns on one decision.

**Keep the existing primitive recognizer; change only what it emits.** Where
`parse_primitive` produces a `depth()` occluder today, it would produce real
geometry — `cyli` → `BRepPrimAPI_MakeCylinder`, `disc`/`ring` → an annular
planar face, `con` → a cone — with leftover raw triangles as planar faces.
Then `BRepBuilderAPI_Sewing` joins them into a shell,
`ShapeUpgrade_UnifySameDomain` merges the coplanar fans, and `ShapeFix_Shape`
repairs the rest.

Sewing the raw soup and skipping recognition is the path to avoid: it turns
every cylinder into 56 planar strips and gives up exactly what the kernel is
being bought for.

## Probe

Throwaway script under `scripts/`, nothing wired into `brick_icons/`. Ordered
so the cheapest kill comes first.

1. **Install + import.** Confirm the arm64 wheel loads under 3.14.
2. **`3001` end to end.** Build from recognized primitives, sew,
   `HLRBRep_Algo`, dump visible edges to a crude SVG. Does it come out as a
   brick, and do the stud rims arrive as circles?
3. **`3942b` — the ragged bore.** Cut the cylinder from the body; check the
   wall/floor boundary is a single exact edge with no tab.
4. **Timing on `3649`.** The real risk. `HLRBRep_Algo` is exact and
   superlinear in edge count, and `3649` already costs 5 minutes today.
   `HLRBRep_PolyAlgo` is the fast fallback but it is polygonal, so it does
   not count as a pass.
5. **Sewing survey.** Build-and-sew across `parts.txt`; report the fraction
   yielding a closed, valid solid. No solid, no boolean, no reliable HLR.

**Kill criteria.** `3649` slower than ~10 minutes, or fewer than ~80% of
`parts.txt` sewing to a valid shell, and the recommendation is no.

If the answer is go, adoption is a separate architectural brainstorm — it is
a rewrite of `hlr.py` and `primitives.py`, not a patch.

## Findings

Measured with `scripts/spike-occt.py` (kept: it re-derives every number below)
against `cadquery-ocp` 7.9.3 in a scratch venv, macOS arm64, Python 3.14.

**Install.** A `cp314`/`macosx_11_0_arm64` wheel exists and works — native
arm64, no conda, no Rosetta. Cost: OCP is 223 MB, and it pulls `vtk`
transitively for another 592 MB. Warm import is 0.54s. The VTK dependency is
dead weight for this repo and worth checking for an opt-out before adoption.

**Exactness holds.** Across `parts.txt`, 720 of 756 recognized primitives
(95%) have an orthogonal, uniformly-scaled frame and map to an exact OCCT
cylinder / cone / annulus; 36 are sheared and would need a fallback. HLR
returns the stud rims as `Geom_Ellipse` and the cylinder limbs as
`GeomAbs_Line` — **the curve type is read off the edge, so `arcfit.py` and
the whole arc-recovery path have nothing left to do.**

**Speed is not the risk it looked like.** `3649`, the 5-minute part, runs
flatten 0.05s + sew 0.71s + unify 0.15s + **exact HLR 0.15s**. The slowest
HLR anywhere in the 48-part survey is 0.21s, and the entire survey —
build, sew, close, fuse, all 48 parts — takes 4.1 seconds. The kill criterion
here was 10 minutes.

**Occlusion is correct, and was checked by eye.** `3001`, `4589` and `3941` reproduce the
current renderer exactly -- right silhouette, right stud count, interior
correctly hidden. `3649` is structurally correct but sits at a different
in-plane rotation from its gallery render, which is view bookkeeping rather
than a geometry error. Getting there took several corrections, every one of
them in the probe's own plumbing rather than in OCCT, and three are worth
carrying into adoption:

- **`HLRAlgo_Projector` does not take `view_basis`'s frame.** OCCT derives
  image Y as `Z x X`, so feeding it `fwd` and `right` pitches the result 90
  degrees. Build the axis as `Z = right x up`, `X = -right`.
- **The axis of `MakeCylinder`/`MakeCone` is the extrusion direction, not
  just the sector reference.** Negating it to correct a left-handed sector
  sweep builds the primitive backwards off its base plane. It does not error
  -- it silently leaves a gap between subparts that reads like a missing
  face. Fix the sweep by rotating the x-direction by `-angle` instead.

- **A 180-degree "pitch" that appears to fix orientation is a reflection.**
  Chasing a part that looked rotated, a 180-degree rotation about the view's
  right axis matched it -- and measures RMSE 0.003 against the mirror of the
  unrotated render, versus 0.344 against the render itself. It is a mirror,
  not a rotation, so adopting it would silently flip chirality on every
  asymmetric part. Symmetric parts (brick, cone, round brick) cannot reveal
  this; it took a gear's spokes. Verify any orientation fix against a chiral
  feature.

Also note `conN`/`ringN` radii are `N+1`/`N` in primitive units, so the
matrix scale multiplies both; using the scale directly as the outer radius
builds a plausible-looking part at the wrong size.

**Robustness.** 48/48 parts build and sew with zero exceptions; 46/48 sew to
a topologically valid shape; 0 HLR failures. Sewing tolerance is irrelevant
between 1e-4 and 1e-1 — shell counts do not move — so the open boundaries are
structural, not numerical.

**The solid problem, and what it actually is.** LDraw parts are assemblies of
*interpenetrating* primitives, not one watertight surface: 3001 sews to 15
separate shells. That is fine -- all 15 are closed, each makes a valid solid,
and `BRepAlgoAPI_Fuse` merges them into one valid solid in 0.04s, with zero
fuse errors anywhere in the survey. With sector faces implemented and the
cone/ring radii and extrusion direction fixed, the baseline is **62% of parts
reaching >=80% closed-solid area and 71% fusing to exactly one solid.**

**Coplanar pre-merge was tried, and it makes things worse: 62% -> 19%.**
Grouping triangles by supporting plane, unioning them in 2D and emitting one
face per region drops coverage hard, and the free-edge measurement says why:
on `2412b` it barely changes the face count (35 -> 33) but drives free edges
8 -> 24 and free-edge length 3.4% -> 46.9%. Merging a plane in isolation
strips the intermediate vertices that the adjacent non-coplanar faces still
carry, manufacturing the T-junctions it was meant to remove.
`ShapeUpgrade_UnifySameDomain` is the right mechanism precisely because it
works on topology and preserves shared vertices.

**`BOPAlgo_MakerVolume` does raise coverage: 62% -> 92%.** It takes a pile of
arbitrary faces and builds the solids they enclose, which is the right shape
of tool for interpenetrating LDraw geometry. With `SetIntersect(True)`,
`SetAvoidInternalShapes(True)` and a fuzzy value of 1e-3 (the knee: 71% at
1e-4, 90% at 5e-4, flat at 92% from 1e-3 up), 44 of 48 parts reach >=80%
closed-solid area, in about 10s for the whole survey. `3001`, `4589` and
`3942b` render correctly from the resulting solids.

**Its failure class is heavily faceted open surfaces.** `3649` yields 102
valid solids covering only 55% of the area, and the render shows why: the
interior cylinders become solids while the gear's faceted outer disc and
teeth never enclose a volume and vanish. This is identical at fuzzy 0, 1e-4
and 1e-3, so it is not a tolerance question. Note that the area metric alone
called this part a partial success -- only the render showed the body was
gone, which is the sheet-is-not-the-renderer trap in a new place.

### Verdict

**Go on the HLR track.** Occlusion is demonstrated visually against the
current renderer on four parts, arc recovery is free, and seam dedupe follows
from shared topology. Those are the bulk of `hlr.py`, `arcfit.py` and
`primitives.py`. Nothing in the measurements argues against it.

**The boolean track is open, not closed.** `BOPAlgo_MakerVolume` clears the
80% bar on 92% of parts, so `BRepAlgoAPI_Cut` is available for the majority
and the ragged bore is reachable. What it does not have yet is an answer for
heavily faceted parts like `3649`, and no measurement here has yet shown the
bore actually fixed -- that needs the cut performed and compared against the
current renderer's tab. Both belong in the adoption design rather than in
this spike.

`ShapeFix_Shell`/`ShapeFix_Solid` were also tried and changed nothing (62%).

### Not answered by this probe

Fills and `--shade-style` were never exercised — the spike stopped at edges.
Whether OCCT's planar booleans replace shapely (and the `4740p03`
`TopologyException`) is untested. Decal carrier binding via
`ShapeAnalysis_Surface` is untested.
