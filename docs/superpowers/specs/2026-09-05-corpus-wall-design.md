# The corpus wall

A pan/zoom wall showing every LDraw part as one cell, so coverage and quality
are things you look at rather than query. For whoever implements it in
brick-icons; assumes the lab, `corpus.db` and `brick_icons/lab/findings.py`, not
weasel's renderer.

The question it answers: **what does brick-icons build so that 24,591 parts are
one navigable surface, given that drawing them fast is weasel's problem?**

## Where it lives

A second app in `lab/`: `corpus.html`, its own React root under
`lab/src/corpus/`, served at `/corpus`. It shares `lab/src/api/client.ts`, the
CSS variables, the vitest setup and the Vite toolchain with the lab.

It becomes a labkit instrument later by importing `<CorpusWall/>`, so nothing in
it may assume the lab's shell, controls or trial state.

## The weasel seam

weasel's mega view — the batched image path, atlasing and level-of-detail
residency — is specified in
`weasel/docs/superpowers/specs/2026-09-05-mega-view-design.md` and unbuilt. Draw
through one component so that landing it is a substitution:

    <Wall cells={…} layout={strategy} thumbs={source} onSelect={…} />

Its body today is labkit's `useTiledSurface` plus core's image and solid draw
commands. 52 image quads and ~24,500 solid quads sit well inside what the
unbatched path carries. When the mega view exists, replace the body; nothing
above `<Wall>` learns what an atlas page is.

## Cells

One cell per row in `parts` — 24,591. A part with a stored render draws its
thumbnail; a part without draws a solid quad colored by status. The wall is a
coverage map before it is anything else.

`/api/corpus/cells` returns all of them in one response: id, title, category,
printed, obsolete, status, the render `sha256` where one exists, and the sort
keys from that part's latest measurement. About 2MB, fetched once at mount.

## Baking

`scripts/bake-thumbs.py` reads `renders.path` and `renders.sha256` and writes
`out/thumbs/<level>/<sha>.png` at 8, 32 and 128 px, plus a manifest mapping part
id to sha to available levels. Keyed on the content hash, so a re-render
invalidates one cell and re-running the bake is idempotent.

Whether atlas pages get composed here or in weasel stays open until the mega
view has an API. Per-item PNGs are its input either way.

## Backfill

`renders` holds 49 naive rows. `out/census-naive/renders/naive/` holds 1,127
SVGs the census kept. Backfill the first 100 through `db.store_render`, which
copies each into `renders/naive/` and records it under the canonical config key.
Skip any id not in `parts`. The count is an argument, not a constant.

## Layout is a strategy

A pure function from cells and a viewport to explicit rects — the shape
`windease` publishes. Day one it is a dense row-major fill in the current sort
order.

Sort keys: part id, category, status, `extra_d99`, `secs`, render age. The
filter bar narrows to unrendered only, errors only, a corpus list, printed, or
obsolete.

Re-sorting emits different rects against the same baked thumbnails; nothing
rebakes. The strategy returns rects rather than a row and column, so the grouped
layout — category blocks separated by whitespace, labels fading in by zoom — is
a second strategy rather than a rewrite of the wall.

## Selection opens a lightbox

Full screen: the render large, every engine's measurement for that part, its
defects, and its run history. The wall keeps its camera behind it, so dismissing
returns you where you were.

Zoom past 128 px swaps a cell's baked PNG for the live SVG. That is level of
detail, not the way you inspect a part.

## Server

Three routes on the existing FastAPI app in `brick_icons/lab/app.py`. A second
server would fork the artifact and defect routes.

- `GET /api/corpus/cells`
- `GET /api/corpus/summary` — `findings.summary`
- `GET /api/thumbs/{level}/{sha}.png`

The lightbox reads through `findings.findings(part=…)` and the existing
`/api/defects`.

## Not in this build

Triage writes, defect editing, the regression gate, atlas pages, and any change
to weasel.

## Traps

**A placeholder cell is not a missing cell.** 24,539 parts have no render and
are the majority of what the wall draws. Placeholders are the common path, not
the error path.

**Do not import from `lab/src/instruments/` or `lab/src/panes/`.** Those are the
lab's, and reaching into them is how the standalone app stops standing alone.
Shared code moves to `lab/src/api/` or a new `lab/src/shared/` first.

**`renders.path` is the artifact; a thumbnail is derived.** Bake from the file
in the store, and never let `out/thumbs/` be the only copy of a drawing.
