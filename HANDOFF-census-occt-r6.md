# Overnight: full occt re-census on studio

Launched 2026-09-07 00:59 EDT. Nothing here is finished; this says what to do
with it in the morning.

## What is running

`onto jobs` — task `census-occt-r6`, job `8ff9b314`, on studio. 8,235 parts in
687 batches of 12, 8 workers, 12h deadline (expires 12:59 EDT). Writes
`out/census/occt-r6`. A fetch stream is pulling it back every 10 minutes.

It is a **full** re-census, not a backfill: `b5b2694` and `c673dd3` changed the
engine, so every existing occt row was measured by a build that no longer
exists. The list is ordered with the 1,576 parts occt previously failed or kept
no render for first, so a night cut short still measures the informative ones.

Synced from a detached worktree at `4905d45`, not from the shared tree — a peer
session had `hlr.py`, `occt.py` and `compare-silhouette-truth.py` uncommitted,
and an unattended run must not measure a half-edited engine.

## In the morning

    onto jobs                                   # finished, or still going?
    pgrep -fl "onto fetch"                      # let the stream's final pass land
    .venv/bin/python scripts/census-coverage.py  # what occt now owes

Then ingest the way `census-round` step 3 says — build into a temp database and
swap it, never in place, because a lab server on 8792 reads `corpus.db` on
every request:

    tmp=corpus.db.ingest.$$
    .venv/bin/python scripts/build-corpus-db.py --out "$tmp"
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);"
    rm -f corpus.db-wal corpus.db-shm && mv -f "$tmp" corpus.db
    .venv/bin/python scripts/bake-thumbs.py

The interesting comparison is not the coverage percentage. It is which of the
405 `TimeoutError` and 238 `ProcessDied` parts now pass, and whether any part
that drew cleanly before regressed — that is what the two engine commits bought.

## Traps this run already hit

`--env PATH=/Users/mike/.local/bin:...` is mandatory: `resvg` lives there and
the agent's PATH does not include it. Without it every part fails in about a
second and `--skip-done` then skips them for good.

studio's agent was rebuilt tonight (BUILD 0907.0049) and lost its configured
limits — a 6h timeout came back clamped to 30 minutes and the work quota
reverted to 10 GiB. Both were reset with
`onto install -max-job-time 12h -max-work-size 40G` on the node. Check the
deadline `onto run` prints; if it is 30 minutes, that happened again.

## The relaunch this run may be superseded by

A peer session has uncommitted `hlr.py` / `occt.py` /
`compare-silhouette-truth.py` work that breaks the render phase into named
subpaths — `render/geometry/engine/hlr` rather than a flat `geometry`. Mike
asked for that granularity, and for the dashboard to show it, on the night r6
launched. r6 is at `4905d45` and carries none of it, so its 8,235 rows are the
newest per part and the finer chart has little to draw until a run at the newer
code replaces them.

r6 was left running anyway: it answers a question the instrumentation does not,
which of the 405 `TimeoutError` and 238 `ProcessDied` parts `b5b2694` and
`c673dd3` fixed. It was not relaunched against the peer's work because that work
is uncommitted, and an unattended overnight run has to name a revision that can
be checked out later.

Once that work is on `main`, the relaunch is:

    git worktree add -q --detach <tmp>/clean HEAD
    cd <tmp>/clean && onto sync -in brick-icons --ref origin/main studio
    onto kill 8ff9b314        # or let it finish; the new rows win either way
    onto run --detach --timeout 12h --in brick-icons --task census-occt-r7 \
      --each out/census/occt-r6-batches.txt --workers 8 --retries 1 --yield \
      --env PATH=/Users/mike/.local/bin:/opt/homebrew/bin:/usr/bin:/bin \
      --out out/census/occt-r7 --to out/census/occt-r7 \
      studio -- scripts/census-batch.sh occt 300 out/census/occt-r7 {}

Its own directory, per `census-round` step 5: a retry beginning with a part that
began an r6 batch would otherwise append to r6's JSONL and `--skip-done` would
read the old rows as done.

Reading the two runs against each other: the OCP import is 0.783s paid once per
worker process, by whichever part a worker draws first. In the new build it is
its own phase; in r6 it is inside that part's geometry. With 8 workers over 687
batches it is a per-batch constant, not a per-part cost.
