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
commands. That path is unbatched, so it carries the wall while the store is
small and stops being enough somewhere on the way to 8,500 thumbnails — which
is the point at which the mega view has to exist. When the mega view exists, replace the body; nothing
above `<Wall>` learns what an atlas page is.

## Cells

One cell per row in `parts` — 24,591. A part with a stored render draws its
thumbnail; a part without draws a solid quad colored by status. The wall is a
coverage map before it is anything else.

`/api/corpus/cells` returns all of them in one response: id, title, category,
printed, obsolete, status, the render `sha256` where one exists, and the sort
keys from that part's latest measurement. About 2MB.

## The store fills while you watch

The render job is ~8,500 unprinted parts and lands them a few at a time, so a
wall that fetched its cells at mount would be stale within minutes and would
show a blank cell for a part that has just been drawn.

Cells carry a monotonic version — the greatest `renders.made_at` in the
response. `GET /api/corpus/cells?since=<version>` returns only the rows whose
render or measurement changed after it. The wall polls it, merges the delta into
the cell list, and re-lays out. Camera, selection and sort survive the merge:
new thumbnails appear where their cells already were.

The bake is incremental for the same reason: it skips a sha it has already
written, so re-running it after each batch costs only the new renders.

## Baking

`scripts/bake-thumbs.py` rasterizes each stored render at 8, 32 and 128 px.
Keyed on `renders.sha256`, so a re-render invalidates one cell and re-running
the bake is idempotent.

The two coarse levels ship as **whole-corpus sprite sheets**, one page each:
`out/thumbs/sheet-8.png` and `sheet-32.png`. 128 px stays loose files at
`out/thumbs/128/<sha>.png` — only a few dozen cells are that large on screen at
once, so they are a residency problem, not a draw-call one.

**A cell's index is its position in part-id order over all 24,591 parts, not a
packing of the parts that happen to be drawn.** An unrendered part still owns
its cell; blank cells cost nearly nothing in a PNG and buy the property that
matters — a render landing mid-session writes one cell instead of renumbering
every cell after it. The sheet at 32 px is 157x157 cells, 5024 px square.

Each sheet ships a JSON manifest beside it: grid pitch, cell size, and the
`sha256` in each occupied cell. The wall diffs the manifest to know which cells
went stale; the sheet itself carries an ETag.

Gutters, per the mega view's bleed trap: level 8 is the coarsest and the mip
chain stops there, so it needs none. Level 32 gets a 2 px edge-replicated
gutter, making its pitch 36 px. Both are decided at bake time and cannot be
retrofitted without rebaking.

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

Triage writes, defect editing, the regression gate, and any change to weasel.

## Traps

**A placeholder cell is not a missing cell.** Most parts have no render, and
even a finished render job leaves ~16,000 of them placeholders. Placeholders are the common path, not
the error path.

**Do not import from `lab/src/instruments/` or `lab/src/panes/`.** Those are the
lab's, and reaching into them is how the standalone app stops standing alone.
Shared code moves to `lab/src/api/` or a new `lab/src/shared/` first.

**`renders.path` is the artifact; a thumbnail is derived.** Bake from the file
in the store, and never let `out/thumbs/` be the only copy of a drawing.

**Never pack a sprite sheet by what is currently rendered.** It is the one
choice that makes every later render rewrite the whole sheet, and it looks
correct until the second batch lands.
