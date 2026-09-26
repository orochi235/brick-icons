---
name: census-round
description: Run a round of the library-scale census on the fleet — stopping what is running, ingesting what came back, working out what is still owed, and relaunching only that. Use on "rerun the census", "ingest what we got back", "what parts are we still missing", "prune the census jobs", or after an engine change that should move which parts finish.
---

## Instructions

The census renders every unprinted library part on another Mac and measures the
drawing against the part's own polygons. A round is: stop, collect, ingest,
diff against the corpus, relaunch the remainder. Every step has a tool already;
this file is the order they go in and the ways each one silently does nothing.

`onto` mechanics — nodes, sync, detach, fetch — are the `onto-job` skill's
subject, not this one. Read it too if you are launching. Getting what came
back into `corpus.db` and onto the wall is `ingest-renders`, which step 3
below is the census half of.

### 1. Stop what is running

    onto jobs
    onto prune <id>          # finishes its current item, starts no more
    onto kill <id>           # SIGTERM then SIGKILL, for one that ignores prune

A batch is a dozen parts, so `prune` can take a batch's worth of wall clock per
worker before the job actually ends. Where the round is going to re-run the
unfinished parts anyway, `kill` costs only the parts mid-render — they come
back in the next coverage list either way.

### 2. Collect before you ingest, and check nobody else is already collecting

    onto returns | head
    pgrep -fl "onto fetch"
    onto fetch --stream <task>

A job launched through `run-slot.sh` already has its stream; one launched any
other way probably has nothing, whatever `--to` was passed. `onto returns`
settles it -- a NEWEST in hours under a job that has been running for hours
means the results are still on the node.

**Two streams on one task race each other into the same directory.** Sessions
share this repo, so a stream is often already running; a second one is not
faster, it is a conflict. `--stream` makes a final pass once the job stops,
which is the only pass guaranteed to see a tree nobody is writing to — so let
it end on its own rather than ingesting the moment the job dies.

### 3. Ingest

    scripts/census-ingest.sh 900     # loop, while a census runs

One pass, by hand:

    tmp=corpus.db.ingest.$$
    .venv/bin/python scripts/build-corpus-db.py --out "$tmp"
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);"
    rm -f corpus.db-wal corpus.db-shm && mv -f "$tmp" corpus.db
    .venv/bin/python scripts/bake-thumbs.py

**Read `ingest-renders` before running either.** It carries the traps that
cost the most time here: a bake is what puts a render on the wall, a rebuild
must go into a temp file and swap, a piped bake reports the wrong exit status,
and a schema bump leaves the lab server 500ing every route until it is
restarted.

### 4. Ask what is still owed

    .venv/bin/python scripts/census-coverage.py --facet white --out out/census-white/todo

Buckets are `drawn`, `redraw` (measured, render not kept), `fails` (every
attempt errored) and `unmeasured` (never attempted). `fails` + `unmeasured` is
"the ones we have not got to yet"; each is written as a plain list, which is
what `--list` and `--each` take.

**Read a facet by `source`, never by `engine`.** Two facets of one engine are
both "naive", so counting by engine reports a part the oracle drew as one this
facet has a render for. `--facet` does this; the default oracle path does not.

The core-hour estimate it prints applies a stored speedup constant to
`measurements.secs`. Both halves are traps: the constants go stale on every
engine change, and **`secs` is the whole oracle pass** — render, rasterize at
zoom 8, truth mask, compare — so a geometry-phase speedup does not transfer to
it. Treat the estimate as an order of magnitude, and re-measure the constant
against the census pass rather than against `hlr.visible_segments`.

### 5. Relaunch only the remainder

Batch the list (a dozen parts a line — `import cadquery` is 6.2s against a
21.6s median part), rsync it to the node because `out/` is gitignored and
`--each` reads its list in the node's own tree, then:

    scripts/run-slot.sh --detach --timeout 12h --in brick-icons --task <task> \
      --each <list> --workers 10 --retries 1 \
      --env PATH=/Users/mike/.local/bin:/opt/homebrew/bin:/usr/bin:/bin \
      --out out/<dir> --to out/<dir> \
      <node> -- scripts/census-batch.sh <engine> 300 out/<dir> {}

- **`run-slot.sh` is `onto run` with the returns wired home** -- a
  `onto fetch --stream <task>` and an `ingest-watch.py` on the tree, both
  started with the job and both refusing to start without `--task` and `--to`.
  A job launched through `onto run` directly delivers only what the agent
  pushes, which on 2026-09-11 was one file apiece across seven running jobs.
  `--no-stream` and `--no-watch` opt out; nothing else does.
- **`--env PATH` is not optional.** The agent's PATH has no `~/.local/bin`, so
  `resvg` is missing and every part fails `FileNotFoundError` in about a second
  — fast enough to write hundreds of error rows before anyone looks, and
  `--skip-done` then skips those parts for good. A launch without it is worse
  than one that crashes.
- **A retry pass needs its own directory.** A batch's JSONL is named for its
  first part, so a retry beginning with a part that began an earlier pass's
  batch appends to that pass's file — and `--skip-done` reads its old timeout
  rows as done and skips exactly the parts being retried. `db.rebuild` rglobs,
  so a subdirectory is still indexed.
- **Get the last round home before relaunching on the same nodes.** The
  relaunch's `onto sync` appears to take earlier jobs' `out/` trees with it:
  on 2026-09-26 the killed `slot-occt-0925`'s tree was gone from studio a
  minute after `slot-occt-0926` synced, and its stream then retried "no such
  path" forever. Compare the tree's rows and drawings here against what the
  job wrote before launching; kill that stream and its watch afterward.
- **Pass `--workers` explicitly.** onto sizes a pool by dividing free memory by
  the task's recorded peak, which for this job is the whole run's figure, not
  one part's — it hands out one worker. 8 on studio, 10 on msb-uai, at ~2.3G
  each.
- **Both nodes must agree on `resvg` and on the LDraw snapshot**, or their rows
  are not comparable and nothing says so. `resvg` is pinned to 0.47.0 in
  `scripts/external-deps.lock`; the antialiasing *is* the comparison reference.

### 6. What a failure bucket is telling you

A `TimeoutError` row is a rendering-cost finding, not a defect. `ProcessDied`
is usually the OCCT segfault in `ShapeUpgrade_UnifySameDomain::IntUnifyFaces`,
which a longer cap will never fix — those parts need the engine, not the round.
A part the watchdog killed is buried as `ProcessDied` by `census-batch.sh` so
it always gets a row; a part with no row at all is invisible to the next
coverage list, which is the one failure mode that loses work silently.
