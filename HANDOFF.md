# Handoff — `main`, with the OCCT engine landed

On **`main`**. 531 tests pass under `BRICK_GOLDENS=full` (~22 min); the render
goldens were re-frozen for the arcfit changes below. A plain `pytest` skips the
drift tests, and `BRICK_GOLDENS=1` renders only `3005` — neither is
verification.

## Read first: there is one thread now

`occt-port` is merged and both its branch and its worktree are deleted, so
this is a single-checkout repo again and the two-workstream protocol below is
history — kept because the lesson still applies if the repo is ever split
again. The port's task briefs, reports and review diffs survive under
`.superpowers/sdd/` (gitignored), moved out of the worktree before removal.

Landed: `50950`'s elliptical wall, arcs read off the projected conic rather
than HLR's BSpline approximation, and a silhouette contour for the OCCT
engine. The defect list below is rewritten against the merged corpus.

## Corpus review 2026-08-31 — the acute-angle family, diagnosed and fixed

One cause explained the boreholes, every gear centre, and the axle's notch
pockets: **`arcfit.fit_edge_arcs` MOVES a fitted chain out of `out["2"]`, and
`occt.authored_loci` built its loci from `out["2"]` alone.** Every chain arcfit
claimed was therefore structurally undrawable in `occt` — silently, because a
locus that matches nothing is not an error. It is the chains at acute junctions
that arcfit claims, which is why the symptom picked out axle holes, gear hubs
and notch pockets and left plain boxes alone. `3941` lost 40 of its 120 type-2
edges that way; `3649` lost 200.

Three fixes, all in `occt.py`:

- fitted chains reach `authored_loci` through `out["fit_arcs"]`, matched as the
  authored chords (the shape's own fragments ARE those chords and miss the arc
  by the sagitta);
- a matched chord fragment is re-read against the fitted circle, so `occt`
  stylizes the chain the way `naive` does instead of drawing two chords meeting
  at a point;
- collinear seg loci merge before matching. `ShapeUpgrade_UnifySameDomain`
  welds collinear edges across subparts, so one fragment can span several
  authored segments and lie inside none of them — `32062` authors its axial
  ridge in five pieces (three `axlehol8` sections plus the two notch spans) and
  gets back one edge running the whole axle.

**`3941`'s naive borehole was never wrong.** The disputed "red herring" call was
right, for a reason nobody had written down: what it draws IS the authored
axle-hole rim — verified edge by edge against the projected type-2 lines, and
against LDView at matched elevation. The near lip is hidden because the front
stud stands 4 LDU proud and, at 30 degrees, its shadow reaches past the lip
(clearing it needs 6.93 LDU of horizontal run against the 4.60 available). Only
`occt` was drawing it wrong, and it drew nothing at all. Re-deriving this costs
an hour; do not re-open it on the strength of the render looking odd.

Two `arcfit` changes, both on the NAIVE path, both re-frozen into the goldens
(12 of 52 cases moved; `A` rises and `L` falls in every one):

- **A neighbouring chord is not a tangent.** It lies half its own sweep off its
  circle's tangent, so on 16-gon tessellation (11.25 degrees against
  `ANCHOR_ANG`'s 15) it reads as a continuation of whatever chain it touches.
  On `3941`'s stud truncation that anchored the fit onto r=4.7 where the chain's
  own vertices sit at 6.8, the residual gate then rejected the chain, and the
  whole truncated quarter drew as a kinked polyline beside the smooth
  270-degree arc. `_fit_circle` now falls back to the unanchored fit when the
  anchored one fails its own residual — and reports zero anchors, so the
  lopsided-chain gate below still applies.
- **`SYM_RATIO` 1.25 -> 3.0.** A real round authored on a slanted plane
  projects to an ELLIPSE, so its sweeps are unequal however evenly it was
  faceted — `54200`'s inner corner is 1.57:1 and drew a 38-degree kink beside
  its own smooth outer ridge. Sited by measurement over the specimen list: real
  rounds run to 2.66, and the first fabricated fit is `32062`'s axle end at
  4.16, which balloons each end into a blob reaching r=6.59 on a part whose
  profile radius is 6.0. Both sides are pinned by tests.

### Still open from that review

- **`4019`'s hub rim.** naive draws a 278.8-degree sweep on a conic of
  semi-axes 13.79 x 10.67; `occt` has that locus, matches one of the eight, and
  draws a different conic (14.88 x 9.11) instead. **Not** `UnifySameDomain` —
  building the shape without it changes neither the sharp-fragment count (481)
  nor the match (1 of 8). Undiagnosed.
- **`4070` (occt): the base ledge's top-front edge is gone.** `4070` has ZERO
  arcfit-claimed edges, so it is not the family above. Still the cleanest
  reproduction of a dropped edge on a simple, fast part.
- **`3673` (naive): only the front notch has its rounded end pocket.** Also
  zero arcfit-claimed edges. The earlier guess that this and `32062` were one
  bug is dead — `32062`'s was the locus gap, and `3673` has no chains at all.
- **`99781`: a vertical line right of the hollow SNOT studs is missing.**
- **`6589`'s misaligned halo on the naive path** — a halo is the signature of
  the counterbore separator refit fixed for `4019` (`SEP_REFIT_MAX_GROWTH`), so
  check whether `6589` has a refit sitting under the 10x cap.

## Read this before calling the port nearly done

**`occt` draws strokes and nothing else.** `occt.visible_segments` returns
`faces=()` and `analytic=()`, so `shade.fill_ops` gets nothing and every filled
mode silently degrades to an outline. It is not "landed with two defects" — it
implements half the renderer:

| mode | naive | occt |
|---|---|---|
| `--shading outline` | yes | yes |
| `--wireframe` | yes | yes |
| `--shade-style flat3` (shaded faces) | yes | **no — no faces** |
| `--opacity` below 1 (transparency) | yes | **no — needs fills** |

Nothing errors when you ask `occt` for a filled render; it just comes back
stroked, which is why this stayed invisible. **Fills is the next body of work,
and `occt` cannot be the default until it exists** — that is a project, not the
two arc defects listed below.

`tests/goldens/hashes.txt` locks the NAIVE engine by construction ("a different
engine fails it by construction"), so `occt` has no corpus gate at all —
`tests/test_occt.py` is the whole of its coverage.

One further open decision, not urgent: the contour's polygonal case, which
fills should absorb rather than fix.

Durable records, none of which this file repeats:

- `docs/superpowers/specs/2026-08-29-occt-adoption-design.md` — where the OCCT
  engine attaches and what gates it.
- `docs/superpowers/plans/2026-08-28-decal-unwrap.md` — decal extraction.
- `docs/superpowers/specs/2026-08-29-pathops-evaluation.md` — the 2D boolean
  question, settled.
- README, **Golden conformance corpus** — how to run the gates and what each
  artifact is for.
- `docs/occt-port-handoff.md` — the OCCT engine's own open defects, and which
  causes are already ruled out for each. It lived at `HANDOFF.md` on
  `occt-port`, which is this file's path on `main`: one path, two different
  documents, so every merge either conflicted or clobbered one of them. It
  keeps its own path now.

## If you ever split this repo across two sessions again

It cost real work twice, both times the same way: a tree that another session
has checked out will move under you mid-task. Uncommitted `occt.py` was
destroyed by a merge, and three separate measurements had to be thrown away
because HEAD changed between the render and the reading. Check `git log -1`
before trusting a tree you did not just commit to, and commit early in one you
share.

**Merge toward the shared branch, never into the other session's checkout.**
Merging `main` INTO the feature branch first turns the final step into a
fast-forward — a pointer move that touches no working tree, so the other
session's uncommitted files survive. That is how this one landed.

**There is no message channel between two sessions here, and the reason is
structural:** peer registries are per-config-dir, so a `~/.claude-pw` session
and a `~/.claude-msb` one never appear in each other's `ListAgents`. The
protocol is a commit to the handoff the other side reads — which works, but
only at commit latency. Give the two documents different paths up front; one
path holding two handoffs conflicted on every single merge.

## The OCCT engine, as merged

`--engine occt` runs OpenCASCADE's exact BRep kernel for hidden-line removal.
`naive` stays the default and its output is byte-unchanged. `brick_icons/occt.py`
is the only module importing OCP; it is an optional extra and raises rather
than falling back, so a part it cannot draw fails loudly instead of being
reported as a pass.

Faces reach `HLRBRep_Algo` as occluders only. The drawn candidates are the
edges LDraw states, which is what keeps a faceted part from exploding: an
unauthored tessellation boundary is never a candidate, rather than a candidate
filtered out.

Both defects this section used to list were the locus gap above, not what they
looked like. `32062` "losing every arc" was never a missing primitive — its
arcs are arcfit chains, and `occt` had no locus for them. `3941`/`6143`
"rendering their truncated studs whole" was the arcfit anchor bug: the
truncation chain was rejected, so the cut drew as chords. Both fixed; see the
corpus review above.

`50950` is fixed: its wall is a true ellipse, which `frame()` rejected as
shear, so no face was built and the slope had no occluder at all. It now draws
3 arcs against naive's 3 and matches naive's shape, closing the unprinted
corpus at 17 of 17.

**`4589` and `3942c` no longer reproduce the cone-base-ring loss** — the ring
is present in both engines and `4589` draws MORE arcs than naive (23 -> 27),
which is not the signature of losing one. Neither was measured the way `50950`
was, so treat this as a symptom that stopped rather than a cause that was
found; `3942c` sitting 4 arcs BELOW naive (32 -> 28) is the loose end.

The rest match naive's shape, and several are markedly cleaner — `3649`,
`4019`, `6589`, `3673` and `32062` each draw less ink for the same drawing.

**`L` counts now run above naive's on curved parts** (`99781` 109 against 29,
`3942c` 56 against 27). That is the silhouette contour, which the OCCT engine
gained this round and which re-fits arcs only where a DRAWN arc exists to snap
to; a curved surface's profile has none. It is SVG size, not ink — the contour
carries outline the per-edge strokes never had, cutting ink naive has and occt
misses from 537 to 378 on `99781` and 335 to 119 on `6143`. It should
evaporate when fills supplies real faces. Do not chase it with a coarser mesh:
the deflection is a quarter pixel because coarser chords poke out from behind
an exact arc stroke.

Evidence for the open two lives in `docs/occt-port-handoff.md`, which also
records, for the stud, which causes are already ruled out.

**The gate is unprinted parts only**, because a print is authored as ordinary
geometry and a strokes-only combo cannot tell it from the part; printed parts
gate `outline-flat3` instead. `tests/goldens/manifest.toml` has the reasoning
and the substitutions.

**Review renders at 0.65 stroke opacity**, not full — `scripts/compare-engines.py
--sheet OUT.png` emits the naive|occt pairs that way. Single strokes read gray
against doubled ink's black, which is how naive's 30–55% duplicate ink becomes
visible at all.

**`--debug-colors` gives every drawn element its own colour** in emission
order. Bare, it is a 12-hue cycle (`trace.DEBUG_PALETTE`) — use it to ask which
element owns a vertex, which a black outline cannot say. `ramp` instead fades
light to dark across 6 elements then steps the hue, so position within a run
and which run both read at once; `ramp=N` sets the run length, and `ramp=100`
trades adjacent-step contrast for coarse structure. It already shows the outer
silhouette is not one contour but many fragments, with the colour changing at
each tangent jog. Opt-in; the goldens do not pass it.

**`--part-label` stamps the whole render tag**, not just the part id:
`3941  naive  30,45  outline` (`cli.render_tag` — part, engine, angle,
shading/style, `opacity=` below 1). Engine and angle print even at their
defaults, because a sheet is read after its command has scrolled away. Pass it
on every render meant for human eyes; it is opt-in and the goldens do not pass
it, so it cannot move the byte-diff gate. `compare-engines.py --sheet` needs it
not — montage already labels tiles `{part}-{engine}`.

**Do not trust any per-part table you find written down, including that one.**
Every recorded table in this repo has gone stale within a day of being
measured — the design doc's, the task-7 report's, and three of mine.
`scripts/compare-engines.py` re-derives it in ~10 minutes and is the only
number worth quoting.

## The decision the merge creates

The stray-geometry defects under **Open** live in
`hlr._visible_segments_analytic`. The standing instruction was not to fix them
because the port would replace that code — but the port has landed *behind a
flag*, so the naive path is still what ships, and it still draws them.

Fix them on the naive path. "Make `occt` the default instead" is not an option
on this timescale: it has no fills, so it cannot render shaded faces or
transparency at all (see the capability table at the top). The naive path is
the only complete engine, and everything filled will keep running on it until
`occt` grows faces.

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

## Open

- **`14769p0a`'s `XI` and `XII` render thinner than `IIII` and `III`.**
  Confirmed present at baseline, cause NOT diagnosed. User's hypothesis: they
  sit farther from the camera. Note they read thinner rather than lighter,
  which foreshortening alone does not explain on a flat top face.
- **`14769px2` throws a stray arc outside its silhouette.** Pre-existing —
  verified identical before and after this work. Unrelated to circle recovery.
- **`4019`'s stray ellipse: FIXED, and it was not what this file said.** It
  was never an analytic rim candidate — it was `_snap_rim_crossings`'
  counterbore separator refit re-emitting a 7.2-degree arc as its 310.8-degree
  complement. `hlr.SEP_REFIT_MAX_GROWTH` bounds the growth; `KNOWN_STRAY` is
  now empty. **`14769px2` above is therefore not "the same class"** — nothing
  has been shown to connect them, so treat it as undiagnosed.
- **Sliver policy: settled.** `unwrap.significant_groups` now carries three
  part-level rules — the sliver ratio, the shatter share, and `MAX_DECALS = 4`,
  which returns nothing when a part still resolves to more than a few textures.
  Sited by eye over the corpus, not by the count alone: above the cap a part is
  always ONE decoration cut across faces, never several prints. `20460p09`'s
  five are panels of the same striped garment; `6580ac01`'s six are one band
  cut four ways. The cap counts SURVIVORS, not raw groups — counting raw would
  silence 52 parts whose single print is intact.
- **The extraction seam has a gate now.** `test_frozen_decal_hashes_still_reproduce`
  diffs `decal-hashes.txt` the way the render seam is diffed; a companion test
  fails if a corpus part has no frozen row. `BRICK_GOLDENS=1` re-extracts one
  part per decal-COUNT class (~8s), `=full` the whole 393-part corpus (~6 min).
  Sampling by count class, not alphabetically, is load-bearing: 310 parts yield
  one decal and 20 yield none, so an alphabetical sample misses both edges —
  which is where `MAX_DECALS` does its silencing.
- **The rim veers down where a notch meets the silhouette, in BOTH engines.**
  On `3941` at `30,65` the outline climbs the notch ceiling, detours to a
  spurious low vertex, then rises to the silhouette:
  `L(193.8,131.7) -> L(198.0,136.3) -> L(201.0,126.7)`. Naive and occt emit
  that same `(198.0, 136.3)` point, so it is NOT an HLR defect — it comes from
  the stage they share (`geom2d.contour_d` / `shade.silhouette_geom`). Fixing
  it there fixes both. Reproduce with `--angle 30,65 --part-label`.
  Two things this explains, so nobody re-chases them: the tangent notch walls
  measure 9.2px against the front notch's 11.8px, and the outline carries a
  visible barb at the tangent. Both appear in both engines. The 9.2-vs-11.8
  split is NOT independent evidence of a naive defect — an orthographic
  argument says equal-height edges project equally, but the two notch corner
  edges sit at different depths and only part of one is unoccluded.
- **`3941`/`6143`'s `stud10` lateral cut: FIXED** — see the arcfit anchor
  fallback in the corpus review. The cut is a cylinder-cylinder intersection
  LDraw approximates with 4 tris and 4 quads; the chain now fits one arc
  through its authored vertices (r=6.8) rather than drawing the chords.
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
- **`BRICK_GOLDENS=1` or the gate does not run — and `=1` is still not the
  gate.** A plain suite reports "N passed, 3 skipped" and those 3 skips are the
  drift tests; two sessions independently mistook that for verification. But
  `=1` renders `3005` ALONE (`--only 3005` in
  `test_frozen_hashes_still_reproduce`), so it passes green through any change
  to any other part. Only `=full` re-renders the 52-case manifest, and it takes
  ~27 minutes. A naive-path change is unverified until `=full` is green.
  `test_drawings_stay_inside_their_own_viewbox` reads the FROZEN json, not a
  fresh render, so it cannot see a fix either until the goldens are re-frozen.
- **`goldens.summarize_svg`'s `bbox` is built from path ENDPOINTS** and never
  samples an arc's sweep, so re-splitting arcs moves it with no ink moving. A
  bbox delta is not on its own evidence that geometry moved;
  `scripts/compare-extents.py` reports reported-vs-swept. Correcting the
  measure would re-freeze every `tests/goldens/render/*.json`.
- **Golden rasters are calibrated against the pinned `resvg` 0.47.0.**
  Upgrading it moves every PNG with no engine change; re-freeze deliberately.
- **Arc parameters are DEGREES** across this codebase. OCCT reports radians; a
  missing `math.degrees` draws a full circle as a 6.28-degree sliver, which
  reads as "broken arcs" rather than as a units bug.
- **`occt_faces` catches every exception and returns `[]`.** Two separate
  defects lost whole surfaces for the life of the port with no error anywhere.
  When touching it, re-run with the `except` removed before believing a `[]`.
- **`cmd | tail` buffers everything until exit** and destroys a progress
  stream. Write results with `--out` and let progress go to the terminal.
- **`ls` is aliased to `ls -la` in this shell**, so `$(ls dir/*.svg | head -1)`
  yields a listing header, not a path. It fails silently in a loop — 46
  rasterizations in a row, each "unable to open". Use a glob.
- **Don't `cd` out of the repo in the same command as a `git stash pop`** — the
  pop fails and the work sits in the stash looking lost.
- **A gate that runs green is not evidence it observes what you think.** Three
  gate-shaped holes were found in one day: a wireframe combo that cannot test
  hidden-line removal because it sets `cull=False`, a cel combo that cannot
  move under an engine swap, and an extraction corpus whose candidate pool was
  an alphabetical prefix containing no classic brick, plate or tile. Ask what
  a gate would MISS before trusting it.
- LDView colour is not evidence; a proof sheet is not the renderer.
