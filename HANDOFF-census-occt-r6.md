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
