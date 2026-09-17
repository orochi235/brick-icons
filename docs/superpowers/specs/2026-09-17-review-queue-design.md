# Review queue

**Status: built, 2026-09-17.** Read the code where it and this disagree.

For whoever next touches how a redrawn part gets judged. The lab page at
`/review` shows every render that displaced an older one, before beside after
beside their diff, with the numbers around the two drawings, and takes a
verdict and a note. A verdict on an entry linked to an open defect updates the
defect, so the defects panel and the wall agree with it.

## Why a record is needed at all

`renders` holds one row per part and slot, and ingest replaces it in place.
The displaced file usually survives on disk only because each fleet round
writes into its own `out/<task>/` tree; a local redraw through `store_render`
writes over `renders/<slot>/<part>.svg` and destroys it. Nothing records which
file a new render displaced. So the before has to be captured at the moment of
displacement, and the capture has to live outside `corpus.db`, which a rebuild
drops and re-derives from the render trees.

## The record

`store-queue/review.jsonl`, append-only, one JSON object per line, the shape of
`store-queue/requests.jsonl`. Every line carries `kind`, `id` and `at`. The id
is `<source>/<part>/<first 12 hex of the after sha>`, so taking the same file
twice writes nothing twice.

- `replaced`: `part`, `source`, `run_id`, `by` (the round's tree name, or
  `lab` for a local redraw), `before` `{path, sha256, made_at, run_id, kept}`
  and `after` `{path, sha256}`. `kept` is where the displaced file was copied:
  `store-queue/before/<source>/<part>.<sha8>.<ext>`, sha-named so a repeat
  costs nothing.
- `diff`: `components`, `pixels`, and `width`, the raster width they were
  measured at.
- `judged`: `verdict`, `note`, `by`, `defects` (ids updated).

`review.fold(lines)` gives the current state per id: the replaced line's
fields, the latest diff, the latest verdict. The database mirrors that in a
`review` table, one row per id, written as each line is appended and replayed
whole by `db.rebuild` after the defects import. Nothing that changes on its own
is stored on the row. Linked defects, the linked redraw request, the builds
and measurements on either side, and whether the entry has been superseded are
all joined at read time.

## Where a line is born

`db.record_render` gains `review_log` and `by`. When the slot already holds a
row and its sha differs from the new file's, it copies the displaced file and
appends a `replaced` line before replacing the row. `review_log=None` turns
this off, and `rebuild` passes it: a rebuild walks every tree in order and
would otherwise log thousands of displacements that never happened in time.
The watcher and `store_render` take the default, `store-queue/review.jsonl`
under root. A slot's first render, a re-take of the same sha, and an older
file refused by the mtime rule write nothing.

The watcher's `--diff` flag measures the diff of each entry it creates as it
creates it, with `lab.diff` at 900 px through resvg, so a round's entries
arrive gated. Without it, or for entries created before it existed,
`scripts/review-diff.py` measures the unmeasured ones in bulk, and the lab
server measures an entry when the page first asks for its diff panel.

## Server

All under `/api/review`, in `brick_icons/lab/review_api.py` registered from
`create_app`.

- `GET /api/review?view=linked|all&min_components=N&judged=0|1&limit=`.
  `linked`, the default, keeps entries whose part has an open defect for the
  slot's engine, or a redraw request made before the after render landed.
  `all` keeps every entry whose measured diff has at least `min_components`
  components, plus unmeasured ones, flagged. Judged entries are dropped unless
  `judged=1`. Newest first. Each entry carries the part's title, both sides'
  `build` (from `measurements` by run and part), `made_at`, `secs`,
  `extra_d99`, `missing_px`, `error` and `edge_scores` row by sha, the diff,
  the linked defects with their `checked` sha for the slot, the request, the
  verdict, and `superseded_by` when the slot no longer holds the after sha.
- `GET /api/review/{id}/before`, `/after`, `/diff.png`. By id only: the row
  names the paths, and no path from the request reaches the filesystem. Before
  serves the kept copy, falling back to the displaced path. After serves the
  after path. The diff panel is `after` faded toward white with every changed
  pixel painted magenta, the same drawing as `scripts/_sheet.py`, and serving
  it records a `diff` line when the entry has none.
- `POST /api/review/{id}/verdict` with `{verdict, note}`. Verdicts are
  `fixed`, `better`, `neutral`, `regression`. Appends the `judged` line, then
  for every open defect on the part naming the slot's engine: sets
  `checked[source]` to the after sha, appends `<date> review <verdict>: <note>`
  to its notes, and sets status `fixed` when the verdict is `fixed`. Each
  defect goes through the TOML and the derived table, as the defects routes do.
- `POST /api/review/measure?limit=N` measures the N newest unmeasured entries
  and returns how many it did.

## Page

`/review`, listed in the switcher as Review, built like `/ingest`: its own
html and entry, `lab/src/review/ReviewPage.tsx`, its own stylesheet. Controls
at the top: Linked / All changes, a minimum-components field that only the all
view uses, a show-judged checkbox, and the count shown. Below, one card per
entry:

- A title row: part id as a link to the lab with `?part=`, the part's title,
  the slot as a material chip, the round name, and when.
- Three panels labeled `before`, `after`, `diff`, the diff's component and
  pixel counts under its label. Panels are `<img>`s at one size.
- A two-column table, before and after, of build, made, run, secs, d99,
  missing px, edge missing of declared, and error. Cells that differ between
  the columns are marked.
- The linked defects, each with id, title, status, and whether its `checked`
  sha is the before sha. The request line when one is linked. A superseded
  notice linking to the newer entry.
- The verdict bar: four buttons, notes textarea. `f` `b` `n` `r` apply to the
  focused card, `j` and `k` move focus. A judged card shows its verdict and
  note instead.

## Tests

- `tests/test_review.py`: a line round-trips; fold takes the latest diff and
  verdict; `record_render` with a differing sha writes the line and the copy,
  and with the same sha or a first render writes nothing; a rebuild replays the
  log; a kept copy survives an in-place overwrite.
- `tests/test_lab_app.py`: the list route joins a defect and a request; the
  linked view drops an unlinked entry and the all view gates on components;
  the image routes answer by id and 404 an unknown one; a verdict updates the
  defect's status, checked and notes and the entry's verdict.
- `lab/src/review/ReviewPage.test.tsx`: renders a card with its three panels
  and both columns; a verdict button posts and the card shows it; the view
  toggle refetches; the switcher lists the page.
