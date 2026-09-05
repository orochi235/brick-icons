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

## Slots: one per engine and style

A **slot** is one drawing of a part — an engine crossed with a style. That is
what `db.py`'s `SOURCES` already enumerates (`naive`, `occt`, `decal`,
`ldview`, `census-naive`, `census-occt`), each with its own argument list in
`_CANONICAL`, so the wall needs no render vocabulary of its own: a slot is a
source.

Every slot gets its own thumbnails and its own sprite sheets. The wall shows one
at a time and can switch between them, which is how you compare what two engines
made of the same part without leaving the wall. `census-naive` is the only slot
with thousands of renders today; `naive` has 49 and the rest have none, so the
source control offers only the slots that have something in them.

Adding a slot is adding a `SOURCES` entry and re-running the bake. Nothing in
the layout, the camera or the wall changes.

## Baking

`scripts/bake-thumbs.py` rasterizes each stored render at 8, 32 and 128 px, one
slot at a time into that slot's own directory.

**Thumbnails are addressed by slot and part number, and `renders.sha256` says
whether one is stale.** A cell on the wall knows its part id and the slot it is
looking at, so those are the name: `out/thumbs/naive/128/3001.png`. The bake
skips a part whose recorded sha matches the one it baked last time, and the
client cache-busts with `?v=<first 8 of sha>`.

A cell's thumbnail is the bare part id under the slot it belongs to.

The two coarse levels ship as **whole-corpus sprite sheets**, one page per slot:
`out/thumbs/<source>/sheet-8.png` and `sheet-32.png`. 128 px stays loose files at
`out/thumbs/<source>/128/<part>.png` — only a few dozen cells are that large on
screen at once, so they are a residency problem, not a draw-call one.

**A cell's index is its position in part-id order over all 24,591 parts, not a
packing of the parts that happen to be drawn.** An unrendered part still owns
its cell; blank cells cost nearly nothing in a PNG and buy the property that
matters — a render landing mid-session writes one cell instead of renumbering
every cell after it. The sheet at 32 px is 157x157 cells, 5024 px square.

Each sheet ships a JSON manifest beside it: grid pitch, cell size, and the
`sha256` baked into each occupied cell, by part id. The wall diffs the manifest
to know which cells went stale; the sheet itself carries an ETag.

Gutters, per the mega view's bleed trap: level 8 is the coarsest and the mip
chain stops there, so it needs none. Level 32 gets a 2 px edge-replicated
gutter, making its pitch 36 px. Both are decided at bake time and cannot be
retrofitted without rebaking.

## Backfill

`renders` holds 49 `naive` rows. `out/census-naive/renders/naive/` holds 2,539
SVGs the census kept, and more land as it runs.

Index them **in place** as source `census-naive`, through `db.record_render` —
never `db.store_render`. `db.rebuild` already does exactly this for
`out/census/renders/*/*.svg`, under the comment "the census's renders stay out
of git but are indexed all the same". Skip any id not in `parts`. The count is
an argument, not a constant.

## Layout is a strategy

A pure function from cells and a viewport to explicit rects — the shape
`windease` publishes. Day one it is a dense row-major fill in the current sort
order.

Sort keys: part id, category, status, `extra_d99`, `secs`, render age. The
filter bar narrows to unrendered only, errors only, a corpus list, printed, or
obsolete, and carries the slot control beside them.

Re-sorting emits different rects against the same baked thumbnails; nothing
rebakes. The strategy returns rects rather than a row and column, so the grouped
layout — category blocks separated by whitespace, labels fading in by zoom — is
a second strategy rather than a rewrite of the wall.

## What a cell's colour says

A cell with no thumbnail is not blank space — it is most of the wall, and its
colour is the only thing it can say. Four states, in this precedence:

| state | colour | source |
|---|---|---|
| an open defect is filed against it | bright ochre `#c8860d` | `defects` |
| it cannot be drawn — GEOS, a dead process, a type error | red `#8c2020` | `measurements.error` |
| the render timed out | dim rust `#5a3326` | `measurements.error` |
| nothing is known | gray `#3a3a3f` | absence |

**A timeout is not a defect.** 1,420 of the 1,428 recorded errors are
`TimeoutError` — the render did not finish, not that the part cannot be drawn.
The eight that genuinely failed would be invisible among them under one colour,
which is the whole reason these are two states rather than one.

**An open defect outranks a failure**, because it is the newer fact and the one
someone acted on. It also applies to cells that *are* drawn: a thumbnail is an
opaque tile, so a background colour would sit behind it unseen, and the cell
gets an ochre ring instead. Defects get filed against parts that render, so
those have to be findable too.

## Selection opens a lightbox

Full screen: the render large, every engine's measurement for that part, its
defects, and its run history. The wall keeps its camera behind it, so dismissing
returns you where you were.

Zoom past 128 px swaps a cell's baked PNG for the live SVG. That is level of
detail, not the way you inspect a part.

## Server

Three routes on the existing FastAPI app in `brick_icons/lab/app.py`. A second
server would fork the artifact and defect routes.

- `GET /api/corpus/cells?source=` — defaults to `census-naive`
- `GET /api/corpus/sources` — the slots that have renders, and how many each
- `GET /api/corpus/summary` — `findings.summary`
- `GET /api/thumbs/{source}/{level}/{part}.png`
  and `/api/thumbs/{source}/sheet-{level}.png`

The lightbox reads through `findings.findings(part=…)` and the existing
`/api/defects`.

## Not in this build

Triage writes, defect editing, the regression gate, and any change to weasel.

## Traps

**Canvas2D runs out at full zoom-out, and the arithmetic says where.**
`paintCommands` builds a 24,591-command frame in 1.05ms, but the draw loop
issues one `drawImage` per cell — at roughly 0.5-1us each that is 12-25ms a
frame, past the 16.6ms budget, and it is all per-call overhead rather than fill
rate. So the wall is smooth zoomed in and degrades only at the extreme where
every cell is on screen. That extreme is what weasel's batched image path
exists for; nothing here should be restructured to avoid it.

**A placeholder cell is not a missing cell.** Most parts have no render, and
even a finished render job leaves ~16,000 of them placeholders. Placeholders are the common path, not
the error path.

**Do not import from `lab/src/instruments/` or `lab/src/panes/`.** Those are the
lab's, and reaching into them is how the standalone app stops standing alone.
Shared code moves to `lab/src/api/` or a new `lab/src/shared/` first.

**`renders.path` is the artifact; a thumbnail is derived.** Bake from the file
in the store, and never let `out/thumbs/` be the only copy of a drawing.

**The census's drawing is not the store's, and must never be filed as one.**
The oracle renders with `--line-width 0 --silhouette-width 0` so its fills carry
the silhouette; the store's `naive` render is the ordinary stroked drawing
`db.canonical_argv` names. Recording one under the other's source files a
drawing under a key describing a different drawing. `db.py` has `census-naive`
and `census-occt` for this. It has been tried and reverted twice — `5cbcd4e`,
and again during this build.

**Never pack a sprite sheet by what is currently rendered.** It is the one
choice that makes every later render rewrite the whole sheet, and it looks
correct until the second batch lands.
