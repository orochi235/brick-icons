# Moving authored data into the database

**Nothing here is built.** This is the shape of a change, written down so it is
not re-derived; the code still works exactly as described under "How it works
today". For whoever picks it up, or decides not to.

## What it is for

Defects and part statuses are authored — a person looked at a render and said
something about it. They should live in `corpus.db`, which is what the database
was made for, and they have to once the wall is hosted: marking a part and
filing a defect are writes, and a hosted wall has no repository to commit into.

## How it works today

`corpus.db` calls itself derived and means it. `db.rebuild` **unlinks the
database file** as its first act and rebuilds every table from the renders on
disk and the git-tracked TOML. The lab's `POST /api/defects` writes
`tests/goldens/defects.toml` directly; the `defects` table is a read cache
filled by `import_defects` on the next rebuild.

So a defect written into the database today survives until the next ingest,
which during a census runs every 900 seconds.

**A live problem, independent of any of this:** the 230 part statuses live in
`tests/goldens/part-status.toml`, which is **untracked**. They are not in git,
not shared between machines, and one `rm` from gone. Worth committing whatever
else is decided.

## The change

**Split the schema by authority.** Authored: `defects`, `notes`, and the
`status` / `status_note` / `status_at` columns on `parts`. Derived: `renders`,
`measurements`, `runs`, `part_years`, `part_successors`, and part identity.

**Rebuild stops destroying.** It already builds into a temp database and swaps
(`census-ingest.sh`); it should carry the authored tables across before the
swap rather than re-importing them from files. Nothing else about the ingest
changes.

**The lab writes to the database.** `brick_icons/lab/defects.py` takes a
connection instead of a path. This is the part that makes a hosted wall work.

**Keep the TOML as an export, written from the database and never read back.**
`corpus.db` is gitignored, so a database-only design leaves the authored data
with no history, no review trail and no way to reach another machine. An export
costs almost nothing — only `db.py` and `tests/test_db.py` reference the TOML —
and keeps the defect list reviewable in git.

The migration is trivial: 17 defects and 230 statuses.

## What this does not settle

Where the authoritative database lives once the wall is hosted, and how a local
session's edits and the server's reconcile. One-way export to git is enough
while the wall is local; it is not a sync protocol.
