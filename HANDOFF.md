# Handoff — OCCT hidden-line port

On **`occt-port`**, in the worktree at `.claude/worktrees/occt-port`. HEAD
`e76596a`, tree clean, 497 passed / 3 skipped. `docs/superpowers/specs/2026-08-29-occt-adoption-design.md`
is the durable record; this covers what changed after it.

**The session that started this port is gone** (its transcript stops at 02:16,
no process holds the worktree). This worktree is unowned — take it. A separate
live session works decal/library restore on `main`; it re-freezes goldens, so
do not land anything that moves `tests/goldens/` without checking with it.

## The facet explosion is fixed at its cause

`build_shape` sewed one face per triangle and drew whatever HLR called sharp,
so every tessellation boundary became a crease — `4740p03` drew 13359 lines
against naive's 2.

**LDraw states its edges; it does not imply them.** Type-2 lines and the `edge`
primitives that carry a rim circle are the creases. Everything else in a mesh
interior is tessellation. Every sewn edge without that backing is now tagged
G1 (`BRep_Builder::Continuity`), which files it under `Rg1LineVCompound`, and
`edges_to_ops` does not draw that compound. An edge that genuinely reads as an
outline still arrives via `OutLineVCompound` — which is exactly what a
conditional line means.

Use the **positive** declaration (type-2), not type-5. `4740p03` authors NO
type-2 edges and naive draws it in 2 lines; tagging from condlines instead
reaches only 5 of its 2401 edges. And never infer from dihedral angle: that
part's cone bands meet at genuinely different pitches and are smooth only by
declaration.

Unprinted parts, drawn L-commands, naive vs occt: `4740` 6/4, `3040b` 41/32,
`3068b` 31/21, `3001` 52/41, `32062` 142/79, `3960` 6/56, `3673` 103/186.

## Next: draw authored edges + silhouette, nothing else

The G1 route has a structural limit — `Continuity` needs TWO faces, and an
edge on one face cannot be tagged, so it defaults to sharp and draws. `3960`
has 326 such edges, `3673` 234. They are unmerged coincident edges the sewing
never stitched; raising `TOL` to a reckless 0.05 LDU only takes 326 to 147.

So stop drawing HLR's `sharp` compound at all. Feed faces to HLR **for
occlusion**, and draw only the authored edges (added to `HLRBRep_Algo` as
edge-shapes, so they are hidden-line-removed against the faces) plus
`OutLineVCompound`. That is naive's model with exact occlusion and exact
curves, and it makes the explosion structurally impossible rather than
filtered: an unauthored boundary is never a candidate, so it cannot leak
through a tagging gap, a sewing crack, or a 1-face edge. `_seg_key` and
`_authored_circles` carry over as the edge source; the G1 tagging retires.

It also kills the doubled ink below, since authored lines are unique by
construction.

## Open defects, measured

- **Doubled ink.** Two 3-point polylines sharing one of their two segments, so
  that leg is drawn twice — `3005`/`3001`/`3040b` at the stud annulus.
  Invisible at full opacity; only the x-ray below shows it.
- **Sliver faces.** `3673` has 77 of 112 paths >60% covered by another,
  including closed micro-triangles; `3941` 56 of 166 retraced, `3649` 66 of
  985. Degenerate faces reaching HLR.
- **`32062` loses every arc** (naive 19, occt 0): a "+"-profile extrusion no
  primitive matches.
- **`3673`'s notch is under-drawn by NAIVE.** Occlusion removes 66 of its 136
  segments. Not a port bug — a place not to match naive.

## Naive is the reference, but it is not ground truth

It lays down **30–55% duplicate ink** on almost every part (share of inked
cells touched by 2+ paths, 0.3-unit grid): `3068b` 54.9%, `3005` 54.5%,
`3040b` 53.7%, `4740` 43.8%, against OCCT's 1–5%. On `4740` it inks 4735 cells
to OCCT's 1575 for a simpler drawing. Converge on naive's *shape*, not its
stroke count, and expect to beat it on duplicates.

## The lab (next project, spans two repos)

Marking regions and paths right/wrong, built on `~/src/weasel` +
`packages/labkit` (weasel gives path hit-testing, area-select and compound
paths; labkit gives `CanvasStack` pan/zoom, `ControlPanel`, `state`
persistence, `trial`/`instrument`). It answers the blocker the spike named:
goldens assert bytes and all go red when output changes by design, whereas a
label asserts geometry and survives an engine change.

**It needs provenance from brick-icons first, or it can only mark pixels.**
Emit a sidecar JSON per render, one row per drawn op: source compound
(`sharp`/`smooth`/`outline`), what backs it (type-2 index, `edge` prim
centre+radius, or silhouette), 3D endpoints, SVG element index. `_edge_ops`
already knows all of this and discards it. Then a label reads "the type-2 edge
p1->p2 is drawn twice" — true of the part, checkable against any engine,
surviving any arc re-split.

The 3D pivot minimap wants NO 3D engine: the thing to pivot is a wireframe of
authored edges, whose 3D endpoints the sidecar already carries, so project
them in JS and draw them as weasel paths. Selection then works identically in
both views against the same anchor, and nothing shades over the edges you are
marking. It matters because HLR bugs are view-dependent — pivoting is how you
separate two coincident strokes, and how you check an edge that vanishes at
30/45 reappears when it should.

## Traps

- **`goldens.summarize_svg`'s bbox is built from path ENDPOINTS** and never
  samples an arc's sweep, so re-splitting arcs moves it with no ink moving.
  91% of `6589`'s recorded 13.93 x-min shift was this; `4589`'s 1.54 and
  `4740p03`'s 4.66 were artifact in full. `scripts/compare-extents.py` reports
  reported-vs-swept. Every `tests/goldens/render/*.json` stores the endpoint
  bbox, so correcting the measure re-freezes all of them.
- **Inlining several rendered SVGs into one HTML page cross-clips them.**
  `trace.py:303` hard-codes `id="sclip"`, so every duplicate after the first
  resolves to the first card's silhouette. Namespace ids per card. The repo's
  own gallery scripts are safe (separate files, rasterized), but a consumer
  embedding an icon set inline is not.
- **Look at overlap with translucent strokes + `mix-blend-mode: multiply`.**
  One stroke reads pale, two read twice as dark. Every duplicate found today
  was invisible at full opacity.
- **A clipPath is not ink.** Counting it put naive's silhouette outset in my
  extent measurement and produced a phantom constant inset on all 23 parts,
  including ones where the engines agree byte-for-byte.
All on **`main`**, working tree clean. 477 tests pass (`BRICK_GOLDENS=1`: 13).
`docs/superpowers/plans/2026-08-28-decal-unwrap.md` is the durable record of
phase 2; this covers what landed on top of it.

**The OCCT port is underway in another session, in its own worktree — do not
start a second one.** First slice is hidden-line removal only, no fills,
behind `--engine occt`, gating on the `outline` combo (`88e1ffd`). Check with
that session before touching `hlr.py` or `primitives.py`. Its first run: 23
parts, 0 render failures, but it does NOT pass — wins where geometry resolves
to analytic primitives, regresses 3x or worse on 9 parts that fall through to
raw triangle facets (`4740p03` 2 -> 13359 lines), and `6589` loses visible
geometry outright. Cause measured as unmerged coplanar facets, not seam edges.

**Do not fix the stray-geometry Open items below.** `14769p0a`'s thin
numerals, `14769px2`'s stray arc and `4019`'s stray ellipse all live in
`hlr._visible_segments_analytic`, which the port replaces — the port session
confirms `4019`'s ellipse disappears under OCCT. Fixing them now is thrown-away
work that collides with that tree.

**Two gates that looked finished turned out to be holes, both found by
review rather than by the tests.** Wireframe cannot gate hidden-line removal
because it sets `cull=False`; the extraction corpus could not catch a
regression in any classic brick, plate or tile because its candidate pool was
an alphabetical prefix containing none. Both are fixed. The lesson worth
carrying: a gate that runs green is not evidence it observes what you think.
Ask what a gate would MISS before trusting it.

## What shipped this session

- `0980599` **skia-pathops evaluated** — adopt, but inside the OCCT port, not
  before it. Conics survive its booleans exactly; it never invents them, so
  the win is unlocked BY the port. Does not replace shapely (no polygon
  offset). Spec: `docs/superpowers/specs/2026-08-29-pathops-evaluation.md`.
- `88e1ffd` **`outline` combo** — 23 strokes-only cases, the isolated HLR gate.
- `b4a89b4` **`outline__4019` added to `KNOWN_STRAY`** — the combo brought the
  part in and the exemption list did not follow, so `main` failed its own
  goldens under `BRICK_GOLDENS=1`. Both 4019 entries retire together.
- `90be857` **decals emit only what is worth looking at** —
  `unwrap.significant_groups`. A torso went 59 SVGs to 1.
- `ced5da9` **candidate pool sampled, not truncated** —
  `scripts/select-decal-candidates.py`.

## What shipped

**`brick-icons decal PARTS...`** — extracts printed decoration as a flat SVG
laid out on the face it came from. Dispatched on `argv[0]` alone, so every
existing invocation parses unchanged (pinned by a test). Documented in the
README under "Decal extraction"; flags are `--out`, `--list`, `--root`,
`--config`, `--texture-px`, `--svg-bg` (transparent by default).

Extraction was emitting **nothing** for every part checked before this. Four
causes, all now fixed and tested:

- Carriers were analytic primitives only, so flat prints bound to nothing.
  Body planes now join them (`planes_from`).
- Discs and rings were used as *curved* carriers. `to_uv` sends every
  non-`Plane` carrier through the cylindrical map, where a flat surface has one
  constant height — a round tile's print unwrapped to a zero-area line.
- A round tile's top face **is** a disc primitive, so it has no facets and
  contributed no plane. Flat primitives now contribute theirs.
- Decoration authored as coloured *primitives* was ignored entirely.
  `3942bp01` is 16 cone sectors and zero coloured facets.

Also: stacked wall sections merge into one spanning carrier (`span_carrier`),
carrier faces union **all** coplanar facets including the print, groups sort by
print area so `.0` is the real print, and `hlr.part_geometry()` skips the view
pipeline (99s → 0.04s on a high-poly torso, byte-identical output, pinned).

**Corpus: 600 parts, 11,855 SVGs, 0 errors.**

## Two deliberate behaviours

**The minifig neck mark is dropped from decals only.** LDraw authors a neck as
a 270-degree body cylinder plus a 90-degree one in black; the head covers it.
It is authored exactly as real print is — `3942bp01`'s stripes partition their
wall into coloured and colour-16 sectors summing to 360 the same way — so it is
caught by position *and* size together: protrudes past the body **and** covers
no more than a quarter of its ring. Either condition alone admits `29030p01`'s
head print and `53983p01`'s turbine case. Renders keep the band, by request.
`scripts/sweep-marker-prims.py` re-derives this over the corpus.

**Circle recovery is per-run, not per-ring.** `fit_circle` asks "is this whole
ring one circle", which a decal boundary usually is not — a union leaves the
coarser polygon's chord midpoints 0.345 LDU inside the rim. `circle_candidates`
clusters vertex radii, **refits each cluster and verifies it**, then `path_d`
converts only the runs that follow one.

## Traps

- **The cluster refit is load-bearing.** Without it, an arch-shaped boundary
  (`14769px2`) fits a meaningless whole-ring centre, invents circles, and
  throws a stray arc outside the silhouette.
- **Never give decal arc candidates a snap tolerance in the render path.**
  Pulling vertices onto the candidate destroyed `14769p0a`'s clock face —
  underside ribs showed through. `shade._decal_arc_candidates` emits the
  candidate only. This is the same hazard as the rim-candidate `NOTE` in
  `hlr._visible_segments_analytic`.
- **`30260p01`'s octagon is the guard for circle recovery** — its 8 vertices
  share a radius, so a circle fits them exactly. Only `ARC_STEP` (45 deg a step
  is too coarse) keeps it a sign. Test pins it.
- **Never `git add -A` in a worktree.** `vendor/` in `.gitignore` matches a
  directory, not the convenience symlink a fresh worktree needs, so `-A`
  commits the link; merging it then checks the symlink out over the real
  directory and a later `reset --hard` deletes the library. That is how the
  pinned 2026-06-27 LDraw snapshot was lost — `complete.zip` serves only the
  latest, so it is gone for good. `/vendor` is now in `.gitignore`; stage
  explicit paths regardless.
- **Don't `cd` out of the repo in the same command as a `git stash pop`** — the
  pop fails and the work sits in the stash looking lost.
- Everything from the previous handoff's Traps still applies: `cmd | tail`
  buffers, subagents park on long commands, LDView colour is not evidence.

## Open

- **`14769p0a`'s `XI` and `XII` render thinner than `IIII` and `III`.**
  Confirmed present at baseline, cause NOT diagnosed. User's hypothesis: they
  sit farther from the camera. Note they read thinner rather than lighter,
  which foreshortening alone does not explain on a flat top face.
- **`14769px2` throws a stray arc outside its silhouette.** Pre-existing —
  verified identical before and after this work. Unrelated to circle recovery.
- **`4019` draws a stray ellipse outside its own viewBox.** Radii 83.79 x
  51.31 across 5 stroke-only paths — larger than the ~134-unit part — pushing
  bbox y-min to -11.08 against `0 0 256 170`. Same class as `14769px2` above
  and the `NOTE` in `hlr._visible_segments_analytic`: analytic rim candidates.
  Pinned by `KNOWN_STRAY` in `tests/test_goldens.py`, which fails if a new
  part joins it *or* if this one gets fixed without the note being updated.
- **Sliver policy: settled.** `unwrap.significant_groups` now carries three
  part-level rules — the sliver ratio, the shatter share, and `MAX_DECALS = 4`,
  which returns nothing when a part still resolves to more than a few textures.
  Sited by eye over the corpus, not by the count alone: above the cap a part is
  always ONE decoration cut across faces, never several prints. `20460p09`'s
  five are panels of the same striped garment; `6580ac01`'s six are one band
  cut four ways. The cap counts SURVIVORS, not raw groups — counting raw would
  silence 52 parts whose single print is intact.
- **The extraction seam has no gate.** `tests/goldens/decal-hashes.txt` is
  written by `scripts/freeze-goldens.py --seam extraction` and read by NO test.
  `test_frozen_hashes_still_reproduce` reads only the render seam's
  `hashes.txt`, and under `BRICK_GOLDENS=1` it re-freezes a single part
  (`--only 3005`); `=full` covers all 54 render cases and still never opens the
  decal hashes. So half the conformance corpus the engine swap is meant to be
  judged on is frozen but unchecked — the cap silenced 19 parts and the suite
  stayed green. Closing this is a test that diffs the extraction seam the way
  the render one is diffed.
- `SNAP_TOL = 0.4` LDU is the loosest constant added, tuned to the 0.345 stray.
  Extraction only; the render path passes no snap tolerance.
- **`skia-pathops` for the 2D booleans: settled — adopt, but inside the OCCT
  port, not before it.** Conics survive its booleans exactly (8 conics out of
  a two-circle union, 4e-7 area error), so it does delete `geom2d`'s arc
  recovery — but only once true circles reach it, and today every polygon is
  pre-flattened by facet tessellation. It also does not replace shapely: no
  polygon offset, which `opened()`, `close_slivers()` and `buffer_d()` need.
  Robustness is not a differentiator. Measurements and the four binding traps:
  `docs/superpowers/specs/2026-08-29-pathops-evaluation.md`.

---

# OpenCASCADE spike — complete, port underway elsewhere

Lives on **`occt-spike`** (4 commits, branched off `1f65166`, nothing merged
to `main`). The durable record is the spec:
`docs/superpowers/specs/2026-08-29-occt-spike.md` **on that branch** — it
carries every measurement, the verdict, and the traps. Read it first; nothing
below repeats it.

Verdict in one line: adopt OCCT for hidden-line removal, and the boolean
track is viable too via `BOPAlgo_MakerVolume`.

## What to do next, and why not the port

**The port is blocked on a question that has nothing to do with OCCT: what
replaces the regression gate?** The net today is 18 specimens byte-identical
to `main`, which stops working the moment output changes by design — every
specimen goes red and none of them tell you whether it broke. Until that has
an answer, a rewrite of `hlr.py` + `primitives.py` cannot distinguish
"different because exact" from "different because wrong". Settle it before
writing port code; it is answerable without OCCT installed.

Then the adoption design. It is smaller than it first looked: replace
occlusion in `hlr.py` and `primitives.py`, delete `arcfit.py`, keep shapely
and `geom2d.py`.

## Traps that are not in the spec

- **`scripts/spike-occt.py` imports `brick_icons.hlr` and `.repair`**, so it
  is pinned to `occt-spike`'s copy of them — now behind `main` by the decal
  commit. Rebase before trusting a re-run.
- **The scratch venv was in a temp dir and is gone.** Recreate with
  `pip install cadquery-ocp` into a throwaway venv; it is ~800 MB with the
  VTK it drags in, so keep it out of `.venv`.
- **`pip` needs `PIP_CONFIG_FILE=/dev/null`** here. A global
  `extra-index-url` points at `us-python.pkg.dev` and prompts for auth, which
  kills any non-interactive install.
- **Coverage numbers need a render behind them.** `BOPAlgo_MakerVolume`
  scored `3649` at 55% area — a partial success by the metric — while the
  render showed the gear's entire body missing. Same class as the existing
  "proof sheet is not the renderer" trap.

## The regression gate: answered

`tests/goldens/` is the replacement, frozen from `main` before any port code.
The reference is the README's **Golden conformance corpus** section — how to
run it, what each artifact is for, and the case manifest. Not repeated here.

What it changes for the port:

- **Judge the port on `scripts/compare-goldens.py`, never on `hashes.txt`.** A
  hash miss is expected and carries no information once output changes by
  design; the comparator ignores hashes and diffs the raster and the
  structural summary instead.
- **Any nonzero delta is real.** Two full freezes of the unchanged engine
  agree exactly — every hash identical, raster RMSE 0.000, no summary field
  moved. The engine is deterministic, so the zero-tolerance defaults hold and
  there is no jitter to explain away.
- **Read the arc/line split as intent.** On round parts `A` rising while `L`
  falls is the kernel doing its job. A round part whose `A` count does *not*
  move is the suspicious one.

Both seams are frozen, since the CLI touches the engine at exactly two points:
the render path (now 54 cases) and extraction via `hlr.part_geometry` (600
parts, 21,035 SVGs, one hash per part, 0 exceptions).

**The `outline` combo is the HLR gate** (23 cases, added `88e1ffd`): strokes
only, occlusion on. `wireframe` sets `cull=False` and is the one combo that
does not exercise occlusion at all; `outline-flat3` does, but its fills take
3001's arc count from 58 to 192 and drown the arc/line signal.

Three things found while freezing:

- **`4740p03` no longer throws `TopologyException`** — not on either seam and
  not in the proof sheet. It is an ordinary decal-heavy specimen in the corpus
  now, so the older handoff's entry for it is stale.
- **The extraction corpus is filtered to parts that have a surface to print
  on**, by `scripts/select-decal-corpus.py`: keep a part with 1..4 carriers at
  least as big as a 1x1 round tile's face, and that also yields something
  through `unwrap.significant_groups`. 393 of 600 candidates survive, carrying
  626 SVGs, every one extracting at least one decal. Sculpted parts — Friends
  legs, minidolls, Simpsons heads — score zero big carriers and drop out;
  wheel-and-tyre assemblies score dozens and also drop. Exceptions belong in
  `corpus-overrides.toml`; `decal-corpus.txt` is generated, so do not edit it.

  **The candidate pool is now sampled, not truncated.** It used to be the first
  600 printed parts in sorted order, so every id started 00-15 and no classic
  brick, plate or tile was in the corpus at all.
  `scripts/select-decal-candidates.py` now takes every-Nth across all 11,220,
  which moved the corpus from 217 distinct shapes to 242 and broke up a single
  shape holding 26% of it. Nothing recorded how the old 600 were chosen, which
  is why the truncation went unnoticed; the pool is a generated file now.

  **Measuring a carrier's area has three traps, all of which silently dropped
  printed round tiles — the class the corpus most needs.** A disc is flat, so
  the wrap-by-height extent a curved carrier reports is zero for one. A flat
  primitive contributes a plane with no facets behind it, so `face.area` comes
  back self-cancelling — 61.9 across a full 40 LDU span on a 2x2 round tile —
  which is why the measure takes the convex hull. And a discretized circle
  measures ~1% under the circle it approximates, so an r=9 carrier misses a
  pi*81 threshold by 0.85%; hence the 5% margin.

  `decal-candidates.txt` is the unfiltered pool: the first 600 printed parts of
  11,220. The slice the decal work reported against (11,855 SVGs) was never
  recorded and this pool yields 21,035, so it is a different 600.
- **Golden rasters are calibrated against the pinned `resvg` 0.47.0.**
  Upgrading it moves every PNG with no engine change; re-freeze deliberately.

---

# OCCT hidden-line port — slice 1 complete, does not pass cleanly

Lives on **`occt-port`** (19 commits, rebased onto `main` at `b4a89b4`, nothing
merged). Durable records, both on that branch:

- `docs/superpowers/specs/2026-08-29-occt-adoption-design.md` — the design, and
  a `## Open` section carrying the measured outcome.
- `docs/superpowers/plans/2026-08-29-occt-hlr-port.md` — the seven-task plan.
- `docs/superpowers/specs/2026-08-29-occt-spike.md` — the spike, copied here
  because it existed on no other ref, with its projector-frame finding marked
  superseded.

Read the design doc's `## Open` first; nothing below repeats it.

## The verdict in one line

`--engine occt` renders all 23 corpus parts with zero failures, wins outright
where geometry resolves to analytic primitives, and regresses by up to 6679x in
line count where it falls through to raw triangle facets. Not a clean pass, and
deliberately not merged.

## READ FIRST: the corpus measurement is STALE

`0aead88` fixed two silent geometry defects found AFTER the corpus run, so every
number in the design doc's `## Open` and in the task-7 report was measured
against broken geometry. **Re-run `scripts/compare-engines.py` and replace those
figures before planning anything off them** (~6 min; `3649` dominates). Both
defects push the same direction as the regression that was measured — phantom
caps add edges and occlude, missing rings remove surface — so the line explosion
and the arc losses are all suspect, not only `6589`.

- `occt_faces` built `cyli`/`con` as CAPPED SOLIDS. `MakeCylinder(...).Shape()`
  is a solid; LDraw's `cyli`/`con` are open lateral surfaces. Ten phantom caps on
  `6589` alone, and a bore cylinder's cap sealed the axle hole, so HLR correctly
  hid geometry behind material the part never had. `.Face()` is the fix.
- No full-circle `ring` ever produced a face. `TopoDS_Wire.Reversed()` is typed
  `TopoDS_Shape`, which `MakeFace.Add` refuses, and the `TypeError` was swallowed
  by `occt_faces`'s blanket `except Exception: return []`. Every full ring in
  every part silently contributed nothing. The bounded-sector path was
  unaffected, which is why it hid so well — and it is a standing argument for
  narrowing that bare `except`.

## What to do next, in this order

1. **The line explosion** on 9 of 23 parts — but re-measure first, per the note
   above; this ranking predates the fix. Previously-measured
   cause is unmerged coplanar triangle facets reaching output —
   `ShapeUpgrade_UnifySameDomain` declining to merge. NOT cylinder seams: those
   were quantified at ~5 of 254 added lines on `3941`, so that hypothesis is
   dead. `tests/goldens/corpus-overrides.toml` and the carrier-count measure in
   `scripts/select-decal-corpus.py` already separate the facet-heavy population
   — same split, different symptom.
2. **Cheap win available:** `out["fit_arcs"]` is computed at `hlr.py:992` and then
   discarded on the OCCT path. Injecting those ops into the result would likely
   recover `32062`'s 19 lost arcs for almost nothing.
3. **`6589`'s bbox x-min shift (13.93), and `4589`'s (1.54).** Both unchanged by
   the bore fix and both undiagnosed. Lower severity than they read in the
   task-7 report, which wrongly tied 6589's to the missing axle hole.

`6589`'s lost bore geometry — item 1 in the previous version of this list — is
fixed: capped-solid cylinders and never-built ring faces, both silent. The
design doc's `## Open` carries it.

## Traps that are not in the specs

- **`occt_faces` catches every exception and returns `[]`.** That is why two
  separate defects lost whole surfaces for the life of the port with no error
  anywhere, and it will hide the next one too: a primitive that raises is
  indistinguishable from one that is deliberately unrepresentable. When
  touching that function, re-run it with the `except` removed before believing
  a `[]`.
- **The frame was settled by enumeration, not derivation.** Three separate
  derivations each looked correct and were wrong. Shipped is
  `Z = +cross(right, up)`, `X = +right`, **Y negated** — a configuration none of
  them proposed. `occt.projector_axes`'s docstring is the authority; the spike's
  `X = -right` is superseded. If you change it, re-run the 8-configuration
  enumeration rather than reasoning about it.
- **The projector test and the chirality test are complementary.** Neither alone
  catches both failure modes: a Z-only flip escapes the chirality test, a
  simultaneous Z+X flip escapes the projector test. Do not delete either as
  redundant.
- **`BRICK_GOLDENS=1` or the gate does not run.** A plain suite reports
  "N passed, 3 skipped" and those 3 skips are the drift tests. Two sessions
  independently mistook that for verification. Gated: 491 passed, 0 skipped.
- **Arc parameters are DEGREES** across this codebase (`hlr.dedupe_segments`
  emits them, `trace._arc_to_svg` and `process.draw_segments` consume them).
  OCCT reports radians. A missing `math.degrees` draws a full circle as a
  6.28-degree sliver, which reads as "broken arcs", not as a units bug.
- **Five tests on this branch could not fail** before review caught them. When
  adding a guard here, mutate the code and watch it go red before believing it.

## Ready-made stress list for the facet-fallthrough regression

From the extraction side (`brick-icons-ac`, 2026-08-30): these 15 parts were
dropped from the decal corpus because their geometry never resolves to analytic
primitives and they shatter into nothing extractable. That is the SAME
population that regresses 3x or worse under the OCCT kernel, so it is a named
stress set for the coplanar-facet merge problem rather than something to
re-derive:

    1006030p01 1006030p02 1011297p04 10128p01 10128p01c01 10128p02
    1022657p03 1023000p03 1023000p04 1023035p04 10830p01 11391p01
    11435p02 13809p02 13809p03

Also: `tests/goldens/decal-hashes.txt` was re-frozen twice on 2026-08-30, ending
at **`ced5da9`** (393 parts / 626 SVGs). Gate against that one, not `90be857`
and not an earlier copy. The RENDER seam is untouched throughout — the 23
`outline__` cases and their hashes are unchanged — but any later slice touching
`hlr.part_geometry` must use the current decal baseline.

**The lesson in that second re-freeze is worth more than the hash.** The decal
candidate pool had been the first 600 printed parts in SORTED order — a prefix
of the id space, not a sample. Every id began 00-15, so the library's largest
printed families were absent entirely (`30xxx` alone carries 1,440 printed parts,
none of them included), the corpus contained no classic brick, plate or tile, and
one shape was 26% of it. A kernel swap gated on that baseline would have left
whole families of geometry unobserved while reporting coverage.

That is the third gate-shaped-hole found in one day, after the cel combo that
could not move under an engine swap and the wireframe combo that cannot test
hidden-line removal. The pattern is the point: **a gate that looks like coverage
is not evidence of coverage until you check what is actually in it.** The
resampled corpus (242 distinct shapes, 41 torsos, printed tiles present) now
spans both the analytic-primitive parts this kernel wins on and the facet-heavy
parts it regresses on, so it is also a better before/after set for the
coplanar-facet merge work than anything derived earlier.
