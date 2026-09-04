# The corpus database

For whoever builds `brick_icons/db.py` and the jobs that fill it. It answers:
where does a rendered picture of a part live, where does a human's verdict on
that part live, and how do you ask whether a part got worse since last week.

Three things have nowhere to live today. A render: the census measured 4,942
parts and deleted all 4,942 drawings, and `out/lab/` is a cache keyed by argv
that is emptied without ceremony. A verdict on a *part* (as opposed to a
defect): `defects.toml` records "this specific thing is wrong", never "this
part has been looked at and is fine". And history: each census run writes its
own JSONL, so "did this regress" is a diff of two files nobody kept.

## One file, `corpus.db`, at the repo root

SQLite. Gitignored — it reaches ~600MB once renders are in it, and every byte
of it is reproducible from the library plus the code that drew it.

Everything a *human* authored is the exception, and it exports to git-tracked
TOML on every write: defects continue to land in `tests/goldens/defects.toml`
in the format `brick_icons/lab/defects.py` already writes, and part statuses
land beside it in `part-status.toml`. The database is the working store; the
TOML is the record that survives `rm corpus.db` and shows up in a diff. Import
runs the other way at build time, so the two cannot drift.

## Schema

```sql
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);   -- schema_version

CREATE TABLE parts (
  id         TEXT PRIMARY KEY,      -- '3001', '4740p03'
  title      TEXT NOT NULL,         -- the .dat's description line
  category   TEXT,                  -- first word of the title, LDraw's own convention
  printed    INTEGER NOT NULL,      -- description says Pattern or Sticker
  obsolete   INTEGER NOT NULL,      -- description starts with ~ or _
  status     TEXT NOT NULL DEFAULT 'unreviewed',
      -- unreviewed | good | suspect | broken | wontfix
  status_note TEXT,
  status_at  TEXT                   -- ISO 8601
);

CREATE TABLE runs (
  id         INTEGER PRIMARY KEY,
  kind       TEXT NOT NULL,         -- 'census' | 'render' | 'lab'
  started    TEXT NOT NULL,
  finished   TEXT,
  commit_sha TEXT NOT NULL,
  args       TEXT NOT NULL,         -- JSON: engine, angle, flags
  note       TEXT
);

CREATE TABLE renders (
  part_id    TEXT NOT NULL REFERENCES parts(id),
  source     TEXT NOT NULL,         -- naive | occt | decal | ldview
  config_key TEXT NOT NULL,         -- lab.cache.key(argv), so the lab agrees
  run_id     INTEGER REFERENCES runs(id),
  made_at    TEXT NOT NULL,
  sha256     TEXT NOT NULL,         -- of the SVG, or of the PNG when there is none
  svgz       BLOB,                  -- gzipped SVG, ~10KB; null for decal/ldview
  png        BLOB,                  -- 512px on the long side, ~25KB
  width      INTEGER, height INTEGER,
  PRIMARY KEY (part_id, source, config_key)
);

CREATE TABLE measurements (
  run_id     INTEGER NOT NULL REFERENCES runs(id),
  part_id    TEXT NOT NULL REFERENCES parts(id),
  engine     TEXT NOT NULL,
  missing_px INTEGER, extra_px INTEGER,
  missing_comps INTEGER,            -- count above the reporting floor
  extra_d99  REAL, extra_d100 REAL,
  secs       REAL,
  error      TEXT,                  -- TimeoutError, ProcessDied, GEOSException…
  detail     TEXT,
  PRIMARY KEY (run_id, part_id, engine)
);

CREATE TABLE defects (
  id         TEXT PRIMARY KEY,      -- the id defects.toml already assigns
  part_id    TEXT NOT NULL REFERENCES parts(id),
  engines    TEXT NOT NULL,         -- JSON array
  status     TEXT NOT NULL,         -- open | fixed | wontfix | notabug
  title      TEXT NOT NULL,
  mark       TEXT,                  -- JSON: the pane-fraction region
  kind       TEXT, points TEXT,
  filed      TEXT NOT NULL
);

CREATE TABLE notes (
  id         INTEGER PRIMARY KEY,
  part_id    TEXT REFERENCES parts(id),
  defect_id  TEXT REFERENCES defects(id),
  written    TEXT NOT NULL,
  body       TEXT NOT NULL
);

CREATE INDEX measurements_by_part ON measurements(part_id, engine);
CREATE INDEX renders_by_part ON renders(part_id);
```

`parts` holds all 24,591 library parts from the first build. `renders` and
`measurements` are sparse against it and always will be — a part with no row
in either has simply never been drawn, which is a fact worth being able to
query.

## Reuse `lab.cache.key` for `config_key`

The lab already canonicalizes an argv into a 16-hex key that ignores flag
order. Using the same function here means a render the lab made and a render
the census made collide correctly instead of storing twice, and it keeps one
answer to "what counts as a different drawing" in the repo.

## What writes it

`compare-silhouette-truth.py` opens a run, writes a `measurements` row per
part, and stores the render when the row trips `worth_keeping`. Its JSONL
output stays: a shard writing to its own append-only file cannot corrupt a
neighbour, and SQLite under eight concurrent writers on a contended box is a
lock-contention problem nobody needs at 3am. **The shards write JSONL; one
importer loads a finished run into the database.**

The lab writes defects and statuses directly — one process, no contention —
and exports the TOML in the same call.

A separate render job fills `renders` for parts nobody has measured, so the
contact sheet can be served from the database instead of rendering a corpus
list as a batch job every time it is opened.

## Build order

1. `brick_icons/db.py`: schema, migrations keyed off `meta.schema_version`,
   and the reader/writer functions. Backfill the 6,125 existing JSONL rows and
   `defects.toml`. Testable with no renders at all.
2. The render job that populates `renders` for a part list.
3. The lab's findings view, reading from the database.
4. The regression gate: a test that fails when a part measures worse than its
   last recorded run.

Each is its own plan. Only the first is specified here.

## Traps

**Do not point the eight census shards at SQLite.** See above; the JSONL is
load-bearing, not legacy.

**A `wontfix` part status is not a `notabug` defect status.** The part status
answers "should this part's renders be looked at again"; the defect status
answers "is this specific claim true". A part can be `broken` with every defect
on it `fixed` — that is the state that says the last fix did not work.

**`printed` and `obsolete` come from the description line, never the id.**
`^\d{3,}p\d+$` catches 3,254 of 13,081 printed parts, and 132 bare-numeric ids
are patterned. The id is a fast path, never the authority.
