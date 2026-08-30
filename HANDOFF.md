# Handoff — decal extraction, then the conformance baseline

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
