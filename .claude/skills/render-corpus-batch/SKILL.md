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
mechanics — nodes, sync, detach, fetch. `ingest-renders` is step 5, and it is
not optional reading: indexing is not baking, and a rebuild that is not swapped
in from a temp file corrupts a database somebody else is reading.

### 1. Survey

    .venv/bin/python scripts/slot-coverage.py

Every slot, emptiest first, with what it would cost per part. `~` on a median
means the slot has no rows of its own and the figure is borrowed from its
engine's other slots — an estimate of an estimate, fine for sizing a batch and
not for quoting.

Three slots cannot be filled from here and the table says so: `ldview` and
`reference` come out of LDView and a browser, and `decal` needs a flag the
census pass does not take.

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

### 3. Launch

`out/` is gitignored and `--each` reads its list in the node's own tree, so
rsync the list across first. Then, with the three values step 2 printed:

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

### 4. Wait, and watch for the two silent failures

    onto jobs
    onto logs <id> | tail -20

A job that is producing nothing looks the same as one that is working. Check
inside the first minute that parts are completing rather than erroring — a bad
`PATH` or a missing `EXTRA` fails everything at about a part a second, and the
run reaches its end having written only error rows.

Do not start a second `onto fetch` on a task that already has one streaming:
two streams race each other into the same directory. `pgrep -fl "onto fetch"`.

### 5. Ingest

    onto fetch --stream slot-occt

Then follow `ingest-renders`. A tree with a `SOURCE` file rides the rebuild
route, because it carries measurements as well as drawings. Let the stream's
final pass finish first — it is the only one guaranteed to see a tree nobody
is writing to, and a part-written SVG indexes fine and bakes as UNREADABLE.

### 6. Report what is owed, not that it finished

Re-run step 1 and say four numbers: asked for, drawn, failed, still missing.
The job's own summary counts what it believes it wrote; `slot-coverage.py`
counts what the database can find. Where they disagree, the disagreement is
the finding.

A `TimeoutError` row is a rendering-cost finding, not a defect. `ProcessDied`
is usually the OCCT segfault in `ShapeUpgrade_UnifySameDomain::IntUnifyFaces`,
which a longer cap will never fix.
