---
name: render-corpus-batch
description: Fill a render slot's gap — survey what each slot is missing, launch a batch on the fleet sized to a wall-clock budget, wait for it, and ingest what comes back. Use on "render a batch", "fill the occt slot", "what slots are we short on", "top up the corpus", or after an engine fix that should make more parts draw.
---

## Instructions

A slot is one `db.SOURCES` entry — an engine crossed with a style — and a part
is missing from it when no `renders` row files a drawing under it. This skill
is one round of closing that gap: survey, pick, launch, wait, ingest.

It measures as it draws. The fill pass is `census-batch.sh`, the same pass the
census runs, so every part comes back with a row saying how the drawing scored
against the part's own polygons. There is no draw-only route here on purpose —
a render nobody measured is a cell on the wall that no coverage number can
check.

Two neighbors own the steps either side of this one. `onto-job` is the fleet
mechanics — nodes, sync, detach, fetch. `ingest-renders` is step 7, and it is
not optional reading: indexing is not baking, and a rebuild that is not swapped
in from a temp file corrupts a database somebody else is reading.

### 1. Survey

    .venv/bin/python scripts/slot-coverage.py

Every slot, emptiest first, with what it would cost per part. `~` on a median
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

### 2. Pick a batch

    .venv/bin/python scripts/slot-coverage.py --slot occt --budget 4 \
        --workers 10 --out out/slot-occt/batches.txt

`--budget` is wall-clock hours on `--workers` workers, and the part count
follows from the slot's own recorded seconds. It prints `ENGINE`, `SOURCE` and
`EXTRA` for the launch — copy them, do not retype them. **`EXTRA` is derived
from `db._CANONICAL` through the CLI's own parser**, so it is the slot's
canonical drawing and not one slot's flags spelled from memory: `occt` states
no stroke width and inherits 2 from the config, where the census pass would
default it to 0 and silently draw `silhouette-occt` instead.

Never-tried parts come before previously-errored ones. A part that times out
costs its whole cap and yields nothing, so a run cut short by its deadline
should spend the time on parts that might succeed.

**`--only never` fills nothing but untried parts, and `--only errored` nothing
but repeats.** Read the `never` and `errored` split before picking: a slot can
be 95% drawn and have a gap that is ENTIRELY repeats, in which case a fill
round buys almost nothing. silhouette-occt reached 19,513 of 20,597 with all
1,084 of its gap errored -- 862 of them `ProcessDied` -- and two jobs spent 43
core-hours re-crashing them for 52 recoveries. A retry round is worth
launching against an engine change and not otherwise; `--only never` is the
default choice for a round nobody has a reason to aim.

A part that ran clean and drew nothing is `errored`, not `never`. It has been
asked and it answered, so a "never tried" set counted as "has no error" will
be wrong -- the other occt facets draw these parts fine and only the
silhouette variant comes back empty. `--only never` writes no file and exits
1 when the class is empty, because an empty batch list launches a job that
dies in seconds with an empty log and reads as the node refusing the work.

### 3. Say what you are about to schedule, before you schedule it

This spends hours of somebody else's machine. Before launching, state in one
short block: **which slot, how many parts, which node, how many workers, the
expected wall-clock, and what will be true when it lands.** Then launch — this
is an announcement, not a request for permission, unless something in it
surprises you.

    slot        white-occt      12,987 parts missing, filling all of them
    node        studio          8 workers, ~4.5h wall clock (~36 core-hours)
    lands as    renders under white-occt + a measurement row per part
    after       white-occt goes from 7,464 drawn to ~12,900 short of failures

**`orochi` is the user's own Mac, and it is the last node you consider, not the
first.** It runs the editor, the browsers, the lab servers and several Claude
sessions, and it is the only machine whose slowness anyone feels. Read its row
in `onto status` last, and dispatch to it only when no other node can take the
work and the job has a reason to need this checkout. A remote node being a bit
busier is not a reason to come home.

**Check no peer session is already working that slot.** Several Claude sessions
share this working directory and cannot see each other's processes. Read their
launch prompts — `ps -eo pid,command | grep '[c]laude'` — before picking, not
after: a slot another session is mid-fetch on will re-render thousands of parts
that are already drawn and waiting to be indexed. `store-queue/*.txt` and
`onto jobs` say what is in flight; neither is enough on its own.

### 4. Launch

**`--each` reads its list in the node's own tree, and `out/` is gitignored, so
the list never arrives on its own.** Copy it first -- the directory does not
exist there either, so `scp` alone fails:

    ssh <node> 'mkdir -p ~/.config/onto/work/brick-icons/out/slot-<slot>'
    scp out/slot-<slot>/batches.txt \
        <node>:.config/onto/work/brick-icons/out/slot-<slot>/batches.txt

Skip it and the job dies in seconds with `exited -1` and an EMPTY log, which
reads like the node refusing the work rather than a missing file. Confirm it
landed (`onto run -in brick-icons <node> -- wc -l < out/slot-<slot>/batches.txt`)
before launching, because once the job holds the tree lock that check 409s.

Then, with the three values step 2 printed:

    onto run --detach --timeout 12h --in brick-icons --task slot-occt \
      --each out/slot-occt/batches.txt --workers 10 --retries 1 \
      --env PATH=/Users/mike/.local/bin:/opt/homebrew/bin:/usr/bin:/bin \
      --env SOURCE=occt --env KEEP=out/slot-occt/renders \
      --env EXTRA='--shade-style flat3 --line-width 2 --silhouette-width 2' \
      --out out/slot-occt --to out/slot-occt \
      <node> -- scripts/census-batch.sh occt 300 out/slot-occt {}

- **`SOURCE` is what files the drawings under the right slot, and what makes
  the tree visible at all.** Without it the tree's name decides the slot, and a
  name with no facet word always derives `silhouette-<engine>` — an `occt` run
  would overwrite the oracle's rows part for part. It is also the only reason a
  tree called `out/slot-occt` is found: the rebuild otherwise takes `out/census*`
  and nothing else, so a fill under any other name comes all the way home and
  indexes as nothing. `census-batch.sh` writes it to `<dir>/SOURCE` from the env
  var, and it travels home with the tree.
- **`KEEP` must point inside this run's own directory.** It defaults to
  `out/census/renders`, so a launch that forgets it drops this slot's drawings
  into the base census tree, where they index as `silhouette-<engine>`.
- **`--env PATH` is not optional.** The agent's PATH has no `~/.local/bin`, so
  `resvg` is missing and every part fails `FileNotFoundError` in about a second
  — fast enough to write hundreds of error rows before anyone looks, and
  `--skip-done` then skips those parts for good.
- **Pass `--workers` explicitly**, and the same number the budget assumed. onto
  divides free memory by the task's recorded peak, which is the whole run's
  figure rather than one part's, and hands out a single worker. 8 on studio, 10
  on msb-uai, at ~2.3G each.
- **Give a retry pass its own directory.** A batch's JSONL is named for its
  first part, so a retry beginning with a part that began an earlier pass's
  batch appends to that pass's file — and `--skip-done` reads the old timeout
  rows as done and skips exactly the parts being retried.

### 5. Check the results are coming home, do not assume they are not

**A detached job that names `--out` and `--to` already delivers as it goes.**
Measured on this round: the job launched at 17:05 and its first renders were
on this machine at 17:06:32, with nobody running a fetch. `readCadence`
defaults to items when no cadence file exists, and `recordDelivery` fires
whenever `--to` is set.

The help text says otherwise and it is worth not believing: `-out` reads
"path under the tree holding this job's results, for a later fetch", and the
launch banner prints `onto fetch --stream <task>` as though that were the step
that starts delivery. It is not -- it is the controller-side pull, useful when
you want a guaranteed-quiet pass after the job stops, and redundant with the
push the rest of the time.

So the check is a check, not a ritual:

    find out/<task>/renders -name '*.svg' | wc -l     # against the job's own count
    onto logs <job-id> | grep -c 'occt@iso'

If those two track each other, delivery is working and there is nothing to
start. If the first stays at zero while the second climbs, THEN something is
wrong -- and `onto deliver --at items <job-id>` is how you turn it on for a
job that somehow has it off.

### 6. Wait, and watch for the two silent failures

    onto jobs
    onto logs <id> | tail -20

A job that is producing nothing looks the same as one that is working. Check
inside the first minute that parts are completing rather than erroring — a bad
`PATH` or a missing `EXTRA` fails everything at about a part a second, and the
run reaches its end having written only error rows.

Do not start a second `onto fetch` on a task that already has one streaming:
two streams race each other into the same directory. `pgrep -fl "onto fetch"`.

### 6b. Start the watcher in the same breath as the job

A render job delivers for hours, and results sitting on disk are results
nobody can query: the wall and every coverage number go on describing the
corpus as it was before the launch. **Start this when you launch, not when
somebody asks what came back:**

    nohup .venv/bin/python scripts/ingest-watch.py out/slot-<slot> \
      --every 300 > out/ingest-watch.log 2>&1 &

It appends — per pass it takes only the parts it has not recorded, then bakes
the slot — so it is not `census-ingest.sh` and must not be confused for it:
that one REBUILDS, dropping and reseeding every table from every tree, which
costs the whole corpus each pass and overwrites what another session ingested
by hand. Name the trees a job is writing to, several if several jobs are
running; a finished tree has nothing to add.

What it makes is what a later rebuild would make of the same tree, so the
rebuild after the job is a no-op rather than a correction.

### 7. Ingest

    onto fetch --stream slot-occt

With the watcher running this is the last mile, not the whole job: let the
stream's final pass land — the only one guaranteed to see a tree nobody is
writing to — and the watcher's next pass takes what it brought. For an SVG
slot a half-written file fails its parse and the next pass takes it whole,
but a truncated raster is only hashed, so `ldview` and `reference` must wait
for that final pass before anything indexes them.

Then stop the watcher and follow `ingest-renders` if the tree needs the
rebuild route for anything the watcher does not carry — part-years, features,
defects, `attempts`.

### 8. Report what is owed, not that it finished

Re-run step 1 and say four numbers: asked for, drawn, failed, still missing.
The job's own summary counts what it believes it wrote; `slot-coverage.py`
counts what the database can find. Where they disagree, the disagreement is
the finding.

A `TimeoutError` row is a rendering-cost finding, not a defect. `ProcessDied`
is usually the OCCT segfault in `ShapeUpgrade_UnifySameDomain::IntUnifyFaces`,
which a longer cap will never fix.
