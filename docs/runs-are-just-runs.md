# Two schema changes for the same quiet hour

**Both unbuilt as of 2026-09-09.** Designed and not implemented, deliberately:
two fleet jobs were feeding the ingest watcher every five minutes, and
changing the shape of a table while one is being written to is the wrong hour
for it. Do both when `slot-occt-r1` and `slot-occt-r2` have landed and the
watcher is stopped.

They are unrelated -- one drops a column nothing reads, the other adds one the
wall has been working around -- and they are here together only because they
wait on the same thing.

For whoever implements them. You know the repo; this says what to change and
what not to.

# Drop `runs.kind`

## The claim

`runs.kind` holds three values — `census` 9 rows, `store` 12, `render` 1 —
and carries no information the database does not already have. Every reader
that keys on it is asking one of two questions it can ask directly:

- **which tree does this run own?** — that is `args.dir`
- **what did it write?** — attempts, or measurements and renders

The word `census` is dead as a run type. It used to separate a sweep that
*measured* from a store run that *drew*; a slot fill now goes through
`census-batch.sh` because measuring is how a fill scores itself, and
`ingest-watch.py` files `census` runs because it followed the rebuild's
convention. Nothing reads the value. Nothing reads `render` either.

**`census` survives as a DIRECTORY convention and that stays.**
`db.census_trees` counts a directory named `out/census*` or carrying a
`SOURCE` marker, and `db.census_source` reads the name to decide the slot.
Out of scope here — do not touch either.

## What keys on it today

Only `store`, only in `db.py`, and both really mean "the run that owns this
tree's attempts":

- `_run_for_tree` (~line 728) — `WHERE kind = 'store' AND
  json_extract(args, '$.dir') = ?`, find-or-create.
- `_stored_attempts` (~lines 750, 757) — carries a pruned tree's attempt rows
  across a rebuild, when its logs are gone and the database is the only copy.

`scripts/ingest-watch.py` `_watch_run` keys on `kind = 'census'` plus
`args.watch`; that one is mine and can key on `args` alone.

Everything else displays it: the ingestion log's leading word, and the part
lightbox's run line (`2026-09-09 · census · 908f80b · occt · d99 1.01`).

## The change

Drop the column. Replace each keyed query with the fact it was standing in
for:

- `_run_for_tree` → `args.dir` alone. A tree has one run; the `kind` filter
  was only keeping it clear of the rebuild's own run for the same directory,
  which no longer exists once every run is a run.
- `_stored_attempts` → the trees named by runs that HAVE attempt rows.
  `EXISTS (SELECT 1 FROM attempts a WHERE a.run_id = r.id)` says exactly what
  `kind = 'store'` was approximating.
- `_watch_run` → `json_extract(args, '$.watch') = 1` and `args.dir`.
- `start_run` loses its `kind` argument; four call sites drop their literal.

The ingestion log's leading word becomes the tree or slot out of `args`,
which is what a reader scans for — `out/slot-occt` says more than `census`
ever did. `ingest.attempts` already works out which table a run filled by
looking rather than by trusting `kind`, so its `kind` field in the response
stays as it is: it describes the ROWS, not the run.

The lightbox run line drops the word; `engine`, `source` and the sha already
say what the row is.

## Migration

There is barely one. `corpus.db` is derived — `db.rebuild` drops and recreates
every table from the trees, so a schema without the column arrives with the
next rebuild. Two things do need care:

- **A snapshot under `out/snapshots` still has the column.** Reading one back
  with the new code must not fail; a `SELECT *` is fine, an explicit
  `kind` reference is not.
- **`_stored_attempts` reads the OLD database while building the new one.**
  It runs against whatever `corpus.db` was before the rebuild, so for one
  rebuild it may be reading a schema with `kind` and writing one without.
  Query it with `EXISTS (... attempts ...)` and it works on both.

## What tells you it worked

- `grep -rn "kind" brick_icons/db.py scripts/` returns nothing about runs.
- A rebuild, then `sqlite3 corpus.db "PRAGMA table_info(runs)"` — no `kind`.
- The ingestion log lists the same runs, led by their tree.
- `tests/test_db.py` and `tests/test_lab_app.py` pass; the ingest tests in
  `lab/src/ingest/` pass.
- Prune a finished store tree (`scripts/prune-store-logs.py`, dry run) — it
  refuses on rows not in `attempts`, which is the path `_stored_attempts`
  exists for.

# Add `parts.touched_at`

## What it is for

Two things, and the second is why it is worth a column rather than a query.

**The wall's delta.** `cells.cells` sends only what changed since the client's
last `version`, and today that version is two values joined by a pipe: the
newest render's `made_at`, and a sha over every judged part. It is two because
a render dates itself and a defect does not — filing one used to update the
lightbox and leave the cell behind it stale, because the delta was built from
renders and no render had happened. The fingerprint is a stopgap for a missing
timestamp. `touched_at` is the timestamp, and the version becomes one value.

**Saying when a part last changed.** A person looking at the wall wants to
know what has moved since they last looked at it, which nothing answers today.

## The rule

`parts.touched_at TEXT`, stamped by every write that changes what a cell
shows: a render landing, a defect on the part filed or re-judged, the part's
own status set. Four writers, all in `db.py`:

- `index_render` / `store_render` — the `INSERT OR REPLACE INTO renders`
- `_DEFECT_UPSERT` and `import_defects`
- both `UPDATE parts SET status=...`

**Write it in the same statement, not from a trigger.** A trigger cannot be
forgotten, which is its appeal, but `db.rebuild` drops and recreates every
table from the trees and a bulk ingest would fire it once per row across
20,000 parts. The writers are four and they are in one file.

## The cost, and it is real

`touched_at` is per PART; the render half of today's version is per SOURCE. A
render landing in `white-occt` will touch a part that the `occt` wall is also
showing, so a client on `occt` gets rows it did not need. They are correct
rows, so this is bandwidth and not staleness — and during a fill the renders
landing are the slot being filled, which is the slot anyone is watching.

Taking the other branch — `touched_at` per (part, source) — buys precision at
the price of a second table and a delta that still cannot see a defect, since
a defect belongs to a part and an engine, not to a slot. Not worth it.

## What tells you it worked

- File a defect with the wall open on a slot that drew the part: the cell
  changes without a reload, and the response carries that one part.
- `cells.cells` has no `_judged` fingerprint and no pipe in `version`.
- A rebuild leaves every part with a `touched_at`, so the first delta after
  one sends everything. That is correct, not a regression.
- `tests/test_lab_cells.py` passes, including the delta tests.
