---
name: ingest-renders
description: Get what came back from a fleet fetch, a bake or a census — the drawings and the rows that measure them — into corpus.db and onto the corpus wall. Use on "ingest the renders", "index what came back", "get it back on the wall", "why is the wall a round behind", "which parts timed out", or after an onto fetch finishes.
---

## Instructions

Renders on disk are the artifacts; `corpus.db` is derived from them and the
wall is derived from the database. An ingest is: check nobody else is doing
it, index, bake, take up the measurements, verify against the files. Every
step has a tool already — this file is which tool for which route, and the
ways each one looks done and is not.

Collecting the renders in the first place is `onto-job`'s subject. Running a
whole census round — stop, collect, ingest, coverage, relaunch — is
`census-round`'s, and it uses this file for its ingest step.

### 1. Check nobody else is already ingesting

Sessions share this working directory and cannot see each other's processes.

    pgrep -fl census-ingest              # the 900s loop, and it is the authority
    pgrep -fl "onto fetch"               # a stream still writing into the tree
    onto jobs                            # a job still producing renders
    ps -eo pid,command | grep '[c]laude' # every session's launch prompt

**`census-ingest.sh` will replace a hand-built database minutes after you swap
yours in**, keeping the files its own scan saw and dropping whatever landed
after. Nothing is lost — the files are the truth — but a count you take a
minute later may be its, not yours. Either index into the database it is
maintaining, or wait a pass and check.

**Ingesting mid-fetch indexes a tree somebody is writing to.** `--stream`'s
final pass, after the job stops, is the only one guaranteed to see it quiet.
A part-written SVG indexes fine and bakes as UNREADABLE later.

### 2. Pick the route by where the renders lie

**A slot under `renders/<source>/`** — `naive`, `occt`, `decal`, `ldview`,
`reference`, `translucent-*`:

    .venv/bin/python scripts/index-slot-renders.py --source occt

Indexes where the files already lie and touches nothing else. Resumable: a
part already recorded under that source is skipped, so a killed run continues
by being run again. `--force` reindexes anyway, which is what a re-bake of the
same slot needs.

**A census tree under `out/census*`** rides on a rebuild, because a tree
carries measurements and defects as well as drawings:

    tmp=corpus.db.ingest.$$
    .venv/bin/python scripts/build-corpus-db.py --out "$tmp"
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);"
    rm -f corpus.db-wal corpus.db-shm && mv -f "$tmp" corpus.db

Into a temp file and swap, always: `db.rebuild` deletes and rewrites, so a lab
server reading mid-pass sees a half-built database. Checkpoint the temp first —
both are WAL, and moving a fresh database over a stale `corpus.db-wal` hands
sqlite a log that is not its own.

**The renders a running census keeps** are the narrow third case:

    .venv/bin/python scripts/index-census-renders.py --limit 100

They file under `silhouette-naive`, not `naive` — a census drawing is
strokeless and its fills carry the silhouette.

**Never rebuild to add one slot.** `db.rebuild` drops the database and reseeds
parts, features, defects, part-years and every census tree with it. It is the
census route's tool, not a bigger version of the slot one.

### 3. Bake, or the wall stays a round behind

Indexing a render does not draw it. The wall draws baked sheets:

    .venv/bin/python scripts/bake-thumbs.py --source occt > out/bake.log 2>&1
    grep -c UNREADABLE out/bake.log; grep -c MISSING out/bake.log

Idempotent by render sha, so it costs only the new parts.

- **Never pipe it.** `bake-thumbs.py | grep | tail` reports *tail's* exit
  status; a bake that died two thirds of the way through a slot is recorded as
  exit 0 and leaves stale sheets. Write a log, grep the file.
- **`UNREADABLE` is a part to re-fetch** — an interrupted fetch leaves
  zero-byte files. The bake logs it and continues rather than abandoning the
  twenty thousand parts after it, so it costs nothing until you stop counting.
- **`MISSING` is a row pointing at a file that is gone.** Those parts are in
  neither the wall nor any missing list, which is how four of them once sat
  invisible for a week.

### 4. Take up the measurements, which are their own ingest

**A drawing and its score arrive together and are ingested apart.** The
`measurements` table has exactly one writer — `import_census_jsonl`, called by
`db.rebuild` over every `*.jsonl` it finds under a directory matching
`out/census*`. Both halves of that are literal: no other script writes the
table, and a tree named anything else is never scanned.

So **the two in-place routes record drawings and no scores.** Index a running
census's renders with `index-census-renders.py` and the wall fills while
`census-coverage.py` still calls those parts unmeasured — only a rebuild
closes it. Check what landed:

    sqlite3 corpus.db "SELECT COALESCE(source,'(null)'), count(*) \
      FROM measurements GROUP BY 1 ORDER BY 2 DESC;"

A `(null)` source is a row imported without its census directory: the reader
can then only fall back to the engine, which does not tell two facets of one
engine apart. `build-corpus-db.py` passes the directory; a hand call to
`import_census_jsonl` has to be given it.

**A render-store run's outcomes ingest as `attempts`:**

    .venv/bin/python scripts/index-store-attempts.py

`store-batch.sh` writes one row per part — `state`, `secs`, `error` — to
`out/store/<dir>/<source>-<part>.jsonl.<source>`, and this takes up every log
under `out/store` into a live database, one run per tree. Idempotent: a second
pass replaces its own rows instead of stacking a copy, so run it whenever a
fetch lands. `db.rebuild` reads the same logs through the same function.

They are not measurements and must not be: every reader there takes the newest
run per part and engine, so a store row would hand each occt finding a null
where its d99 was.

    sqlite3 corpus.db "SELECT source, COALESCE(error, state) AS outcome, \
      count(*) n, ROUND(AVG(secs),1) avg FROM attempts GROUP BY 1,2 \
      ORDER BY n DESC;"

**A timed-out part leaves no render and no measurement, so its `attempts` row
is the only record it was tried.** Read the failures out of there — they are
what the next pass is owed:

    sqlite3 corpus.db "SELECT part_id, secs FROM attempts \
      WHERE source = 'occt' AND error = 'TimeoutError' ORDER BY part_id;"

**`scripts/render-store-report.sh` will not tell you this.** It globs
`out/store/s*.jsonl.*` and `shard-*.txt` — the old local-shard layout — so
against a fleet run's directory it reports an older run's numbers rather than
finding nothing, which is the worse failure of the two. The `attempts` query
above is the honest version.

### 5. Prune a finished tree's logs, once the rows are somewhere else

The logs are two things at once — the record we ingest, and the resume state
`Runner.remaining()` reads to decide what a relaunch still owes. So a live
task's logs stay, and pruning is per finished tree:

    sh scripts/snap-corpus.sh                       # VACUUM INTO, about a second
    .venv/bin/python scripts/prune-store-logs.py out/store/<dir>
    .venv/bin/python scripts/prune-store-logs.py out/store/<dir> --delete

Dry run without `--delete`. It refuses on a marker written in the last half
hour, on logs still being written, on any row not in `attempts`, and unless a
snapshot under `out/snapshots` **holds those rows itself** — checked by
counting them there, because a snapshot taken after the logs can still predate
the ingest.

**Deleting a log makes the database the only copy of those rows.** A rebuild
carries them across from the database it replaces, so a pruned tree survives
one — but only while some database still has them, which is what the snapshot
is for. The node keeps its own tree, so pruning here does not stop a relaunch
resuming there.

### 6. Verify against the files, not against the run

    ls renders/<slot> | wc -l
    sqlite3 corpus.db "SELECT source, count(*) FROM renders GROUP BY source ORDER BY 2 DESC;"

A job's own summary counts what it believes it wrote. These two count what is
there. Where they disagree, the disagreement is the finding.

### 7. Restart the lab server after a schema bump

`db.connect` raises when the file is at a higher schema than the code, so a
server started before a bump 500s every database route — the blank wall that
reads like an ingest failure. There is no `--reload`:

    pkill -f "brick_icons.lab --port 8792"
    .venv/bin/python -m brick_icons.lab --port 8792

It is shared with the other sessions in this directory, so say so when you
bounce it.

### 8. Report what is owed, not that it finished

An ingest ends with four numbers: what came back, what indexed, what failed,
and what is still missing from the slot. "Ingested and baked" without them
says nothing about whether the round is done — and the failures are in the
JSONL, not in anything the database will show you.
