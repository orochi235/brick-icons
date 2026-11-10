---
name: render-corpus-batch
description: Fill a render slot's gap or redraw what an engine change outdated — survey what each slot is missing or outdated, launch a batch on the fleet sized to a wall-clock budget, wait for it, and ingest what comes back. Use on "render a batch", "fill the occt slot", "what slots are we short on", "top up the corpus", "redraw what is stale", or after an engine fix that should make more parts draw.
---

## Instructions

A slot is one `db.SOURCES` entry — an engine crossed with a style — and a part
is missing from it when no `renders` row files a drawing under it. This skill
is one round of closing that gap, or of redrawing what an engine change has
left outdated: survey, pick, launch, wait, ingest.

It measures as it draws. The fill pass is `census-batch.sh`, the same pass the
census runs, so every part comes back with a row saying how the drawing scored
against the part's own polygons. There is no draw-only route here on purpose —
a render nobody measured is a cell on the wall that no coverage number can
check.

**Launch through `scripts/refill-slot.sh`, not `onto run`.** It computes the
list at launch and hands it to `scripts/run-slot.sh`, which is `onto run` with
the nodes readied and the job's returns wired home as part of the launch --
the fetch stream and the ingest watcher -- and opting out of either is a flag
you have to type.

Two neighbors own the steps either side of this one. `onto-job` is the fleet
mechanics — nodes, sync, detach, fetch. `ingest-renders` is step 7, and it is
not optional reading: indexing is not baking, and a rebuild that is not swapped
in from a temp file corrupts a database somebody else is reading.

### 1. Survey

    .venv/bin/python scripts/slot-coverage.py

Every slot, most owed first -- missing and outdated together -- with what it
would cost per part. `~` on a median
means the slot has no rows of its own and the figure is borrowed from its
engine's other slots — an estimate of an estimate, fine for sizing a batch and
not for quoting.

Two slots cannot be filled from here and the table says so: `ldview` and
`reference` come out of LDView and a browser.

**`decal` is filled by a different pass.** It has no silhouette to score
against, so there is nothing for `census-batch.sh` to measure and its route is
`scripts/build-render-store.py --sources decal`, sharded by list and launched
the same way. Its scope is narrower too -- `SLOT_SCOPE` in `slot-coverage.py`
counts only decorated parts, because a plain brick is not missing a decal.

**Prefer an occt slot.** occt is the engine under work; a naive slot is
low priority unless someone asked for it, and naive is also the half that
still fails stickers.

### 2. Pick what to draw

The survey's two columns are two different jobs. **`missing`** is a fill: parts
with no drawing in the slot. **`outdated`** is a redraw: parts whose drawing
was measured before the engine's last change (the last commit under
`brick_icons/` outside `lab/`), so the slot shows a picture the engine no
longer draws. Reference slots are never outdated -- LDView or a browser drew
them. A slot short a few hundred parts and outdated by twenty thousand wants
the redraw.

    .venv/bin/python scripts/slot-coverage.py --slot white-occt --only redraw \
        --budget 4 --workers 32

`--budget` is wall-clock hours on `--workers` workers, and the part count
follows from the slot's own recorded seconds. **Those seconds are history**:
they were measured at older builds, and an engine that got faster since makes
the estimate high -- 2026-09-30's occt redraw was budgeted at 186 core-hours
and took about 24. Size the announcement from the last round's measured rate
when there is one. `redraw` takes the cheapest parts first.

Never-tried parts come before previously-errored ones. A part that times out
costs its whole cap and yields nothing, so a run cut short by its deadline
should spend the time on parts that might succeed. A part whose latest attempt
at the slot's current build timed out after at least `CAP` seconds is
`outlasted` and no pool takes it: the same engine can only time out again. An
engine change makes it `stale` and lets it back in.

**`--only never` fills nothing but untried parts, and `--only errored` nothing
but repeats.** Read the `never` and `errored` split before picking: a slot can
be 95% drawn and have a gap that is ENTIRELY repeats, in which case a fill
round buys almost nothing. silhouette-occt reached 19,513 of 20,597 with all
1,084 of its gap errored -- 862 of them `ProcessDied` -- and two jobs spent 43
core-hours re-crashing them for 52 recoveries. A retry round is worth
launching against an engine change and not otherwise; `--only never` is the
default choice for a fill nobody has a reason to aim.

**`--only crashed` is the retry round for a crash fix**: the errored parts
whose latest attempt was `ProcessDied`. Timeouts and Python exceptions stay
out, and so does a part that crashed once and has timed out since.
`MemoryError` is an exception, not a crash, and is not included.

A part that ran clean and drew nothing is `errored`, not `never`. It has been
asked and it answered, so a "never tried" set counted as "has no error" will
be wrong -- the other occt facets draw these parts fine and only the
silhouette variant comes back empty. An empty class writes no file and exits
1, because an empty batch list launches a job that dies in seconds with an
empty log and reads as the node refusing the work.

### 3. Say what you are about to schedule, before you schedule it

This spends hours of other machines. Before launching, state in one short
block: **which slot, how many parts, which nodes, the worker ceiling, the
expected wall-clock, and what will be true when it lands.** Then launch — this
is an announcement, not a request for permission, unless something in it
surprises you.

    slot        white-occt      20,386 outdated, redrawing all of them
    nodes       the fleet       32 workers at most, ~1.5h wall clock (~25 core-hours)
    lands as    renders under white-occt + a measurement row per part
    after       white-occt drawn at build 1729 throughout

**The user's own Mac -- the controller, `onto id` -- never takes a round.** It runs the editor,
the browsers, the lab servers and several Claude sessions, and it is the only
machine whose slowness anyone feels. `run-slot.sh` leaves it out of `any` (see
below); name it only when the job genuinely needs this checkout.

**Check no peer session is already working that slot.** Several Claude sessions
share this working directory and cannot see each other's processes. Read their
launch prompts — `ps -eo pid,command | grep '[c]laude'` — before picking, not
after: a slot another session is mid-fetch on will re-render thousands of parts
that are already drawn and waiting to be indexed. `store-queue/*.txt` and
`onto jobs` say what is in flight; neither is enough on its own.

### 4. Launch

One command computes the list at launch time and dispatches it:

    scripts/refill-slot.sh occt any slot-occt-r<n> --budget 4
    scripts/refill-slot.sh white-occt any slot-white-occt-r1729 --only redraw --budget 99

`any` hands the round to onto, which spreads it over every node ready for it
(`--any --spread 0`) and cuts the list into batches as it hands them out
(`--batch 12`), so the last batches are a part or two rather than a dozen
stranding one worker. A node name instead of `any` pins the round there.
`--workers` is a ceiling for the whole task, 32 under `any`; onto sizes each
node from its free cores under it. `--only redraw` also passes the watcher
`--overwrite` (step 6b), without which a redraw indexes nothing.

What the two scripts do so a launch cannot get them wrong -- and why a
hand-built `onto run` is the wrong tool:

- **A node joins only when its tree draws at this checkout's build.** Every
  row records the build that drew it, so a node trailing HEAD spends its run
  producing parts that land still outdated. `run-slot.sh` asks each enrolled
  node for `brick_icons.build()`, runs `onto sync` where it differs or this
  checkout is dirty, and under `any` leaves out a node it cannot ready (no
  tree, no `.venv`, a job holding the tree, a sync refused) with the reason
  printed. A node fetches its base from origin, so **a checkout ahead of its
  upstream never matches**: push, or pass `--sync-from <clean worktree at
  origin/main>`.
- **The list reaches every readied node.** `out/` is gitignored, so no sync
  carries it, and a job missing it died in seconds with an empty log that read
  as the node refusing the work. `run-slot.sh` copies it to each, and passes
  `--needs vendor/ldraw --needs .venv --needs <list>` so onto skips any node
  without them -- which is also what keeps this machine out: it is never readied, so
  it never holds the list.
- **`EXTRA` is derived from `db._CANONICAL`** through the CLI's own parser and
  read from slot-coverage's output, never retyped: leave the stroke widths out
  and the census pass defaults them to 0, silently drawing `silhouette-occt`.
- **`SOURCE` files the drawings under the right slot**, and is what makes the
  tree visible at all. Without it the tree's name decides, and a name with no
  facet word derives `silhouette-<engine>` -- an `occt` run would overwrite the
  oracle part for part. `census-batch.sh` writes it to `<dir>/SOURCE`, and it
  travels home with the tree.
- **`KEEP` points inside the round's own directory.** It defaults to
  `out/census/renders`, where a slot's drawings index as `silhouette-<engine>`.
- **`--env PATH` carries `~/.local/bin`.** Without it `resvg` is missing and
  every part fails `FileNotFoundError` in about a second -- fast enough to
  write hundreds of error rows before anyone looks.
- **`HARD` sits 300s above the cap.** The watchdog kills a part in flight past
  it and records `ProcessDied`, so a watchdog under a raised cap buries every
  part the cap was raised to reach, as a crash.
- **Every round gets its own directory**, `out/<task>`. A batch's JSONL is
  named for its first part, so a retry beginning with a part that began an
  earlier pass's batch appends to that file -- and `--skip-done` reads the old
  rows as done and skips exactly the parts being retried.

A node that is not provisioned at all -- no tree, no `.venv`, no LDraw library
-- gets `scripts/provision-node.sh <node>` once; after that `any` takes it in.

### 5. The returns are wired at the launch, not chased afterwards

`run-slot.sh` is `onto run` plus the two instruments that get results home and
into the database: an `onto fetch --stream <task>` and an `ingest-watch.py` on
the tree. Every other flag passes through untouched, so there is no second
launch interface to keep in step, and it refuses a launch with no `--task` or
no `--to` because both instruments key on those. `--no-stream` and `--no-watch`
opt out; say in the same breath what will collect the job instead.

**Do not trust `--to` to deliver on its own.** It records a destination and the
agent does push to it, sometimes: on 2026-09-11 seven running jobs had
delivered one file apiece while 10,000 sat on their nodes, and four hours of
renders were invisible to every coverage number and to the wall. Nothing
reports this -- `onto jobs` says running, the logs say drawing, and the local
tree simply stops growing.

So the check is a real check:

    onto returns | head                # FILES and NEWEST, per task
    onto fetch --dry-run <node>:brick-icons/out/<task> out/<task>

The dry run names the gap in files and MiB and moves nothing. A NEWEST in hours
under a job that has been running for hours is the failure.

### 6. Wait, and watch for the two silent failures

    onto jobs
    onto logs <id> | tail -20

A job that is producing nothing looks the same as one that is working. Check
inside the first minute that parts are completing rather than erroring — a bad
`PATH` or a missing `EXTRA` fails everything at about a part a second, and the
run reaches its end having written only error rows.

Do not start a second `onto fetch` on a task that already has one streaming:
two streams race each other into the same directory. `run-slot.sh` checks
before it starts one; by hand, `pgrep -fl "onto fetch"` first.

### 6b. What the watcher is doing while you wait

`run-slot.sh` started it; this is what it is. Per pass it takes the parts it
has not already recorded and bakes the slot, so the wall and the coverage
numbers track the job instead of describing the corpus as it was before the
launch. It appends.

**It is not `census-ingest.sh` and must never be confused for it**: that one
REBUILDS, dropping and reseeding every table from every tree, which costs the
whole corpus each pass and overwrites what another session ingested by hand.

What the watcher makes is what a later rebuild would make of the same tree, so
the rebuild after the job is a no-op rather than a correction.

**A round that REDRAWS parts the slot already holds needs `--overwrite`, and
without it the whole round ingests nothing.** `_take_renders` skips any part
already filed under the slot, which is right for a fill and exactly wrong for
a refresh: on 2026-09-16 a 7,379-part occt re-render at a newer engine fetched
every drawing home and left `renders` untouched, and nothing said so -- the
watcher logged its passes, the tree filled up, and the slot's build stamps did
not move. Add `--overwrite` at launch when the batch list came from parts that
are already drawn.

Started by hand -- a job someone else launched, or a stream restarted after a
gap -- it is:

    nohup .venv/bin/python scripts/ingest-watch.py out/slot-<slot> \
      --every 300 --until <task> > out/ingest-watch-<task>.log 2>&1 &

`--until` is what closes the round on its own: while onto still lists the task
the watch keeps going, and once it does not, one last fetch and one last pass
end it. Without it the watcher runs forever over a finished tree.

### 7. Ingest

With step 4's stream and watcher up, this step is already happening and the
round closes itself: the stream's final pass is the only one guaranteed to see
a tree nobody is writing to, and the watcher's `--until` waits for it before
its own last pass.

For an SVG slot a half-written file fails its parse and the next pass takes it
whole, but a truncated raster is only hashed -- so `ldview` and `reference`
must wait for that final pass before anything indexes them.

Then follow `ingest-renders` if the tree needs the rebuild route for anything
the watcher does not carry -- part-years, features, defects, `attempts`.

### 8. Report what is owed, not that it finished

Re-run step 1 and say four numbers: asked for, drawn, failed, still missing.
The job's own summary counts what it believes it wrote; `slot-coverage.py`
counts what the database can find. Where they disagree, the disagreement is
the finding.

A `TimeoutError` row is a rendering-cost finding, not a defect. `ProcessDied`
is usually the OCCT segfault in `ShapeUpgrade_UnifySameDomain::IntUnifyFaces`,
which a longer cap will never fix.
