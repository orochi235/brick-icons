# Handoff — decal extraction as a first-class feature

Merged to **`main`**. 462 tests pass.
`docs/superpowers/plans/2026-08-28-decal-unwrap.md` is still the durable record
of phase 2; this covers what landed on top of it.

**Next up is an engine swap.** The seam is narrower than it looks: the CLI
touches the engine only through `hlr.visible_segments` (view path) and
`hlr.part_geometry` (extraction, no view). Keep the naive engine on `main`
behind an `--engine` selector rather than on a long-lived branch — a branch
stops being exercised and rots. Freeze golden outputs from the naive engine
first, so drift is detectable: the specimen gates plus the 600-part decal
corpus run are already most of a conformance suite.

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
- **A quarter of printed parts emit 21+ textures**, nearly all slivers (a
  modern torso: 58, of which `.0` and `.1` are front and back). Ordering makes
  the right one first; whether to add a minimum-area threshold, go
  dominant-only, or leave it is an undecided product call.
- `SNAP_TOL = 0.4` LDU is the loosest constant added, tuned to the 0.345 stray.
  Extraction only; the render path passes no snap tolerance.
- **Evaluate Skia / `skpathops` for the 2D path booleans.** The adoption
  sketch below keeps shapely, which flattens arcs through every boolean and is
  what makes arc recovery necessary downstream. If `skpathops` preserves
  conics it competes with that whole step, not just with shapely. Open
  questions: the Python binding (`skia-python` vs the standalone `pathops`
  wheel), and whether it also answers the `4740p03`-class `TopologyException`.

---

# OpenCASCADE spike — complete, port not started

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
the render path (31 cases) and extraction via `hlr.part_geometry` (600 parts,
21,035 SVGs, one hash per part, 0 exceptions).

Three things found while freezing:

- **`4740p03` no longer throws `TopologyException`** — not on either seam and
  not in the proof sheet. It is an ordinary decal-heavy specimen in the corpus
  now, so the older handoff's entry for it is stale.
- **The 600-part decal corpus is pinned in `tests/goldens/decal-corpus.txt`.**
  The full printed set is 11,220 parts; the slice the decal work reported
  against (11,855 SVGs) was never recorded, and this one yields 21,035, so it
  is a different 600. Pinned rather than re-enumerated so an LDraw update
  cannot move it silently.
- **Golden rasters are calibrated against the pinned `resvg` 0.47.0.**
  Upgrading it moves every PNG with no engine change; re-freeze deliberately.
