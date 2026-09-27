---
name: vet-fix
description: Take an engine fix from "it works on my part" to merged on main — diff it on the defect's own part, then on a handful of parts likely to share the defect, then across the goldens, with a person's review wherever it is asked for. Use when a fix for a defect is ready to test, on "test this fix", "vet the fix", "is this ready for main", or before committing any change that moves a drawing.
---

## Instructions

A defect is almost always filed against one part, and a fix is judged in
widening circles around it. Each gate either stops the fix or passes it on.

| gate | parts | passes when | stops when |
|---|---|---|---|
| 1. the part | the defect's own part | the drawing moved, and the defect is gone | nothing moved |
| 2. the cohort | 5–10 parts most likely to share the defect | none of them is worse | any one is worse |
| 3. the goldens | the parts in `tests/goldens/manifest.toml` | nothing moved that was not expected to | — an unexpected change goes to review |

Once gate 3 passes, the fix is **approved**: commit it on `main`, and the next
census round redraws it. Each redraw that replaces a render lands on the lab's
`/review` page. Judging it "fixed" there closes the defect, so approval does
not close the defect by itself.

### Every sheet is a before/after/diff from one tree

At every gate the evidence is the sheet CLAUDE.md describes: `before`,
`after`, and a third panel painting the changed pixels over a faded `after`,
with a count of the changed regions. `scripts/_sheet.py` draws it. Both sides
come from the SAME tree. Get `before` by disarming the new code in-process, as
`scripts/tail-before-after.py` does, or from a worktree at the base revision
run with `PYTHONPATH=$PWD`. Never stash or check out in the shared checkout.
Post the sheet to the wall at every gate, including a gate that passed.

Judge by counting changed regions (connected components), not changed pixels.
Antialias fringe makes hundreds of specks; a real change is a few chunky
regions.

### Manual review

Any gate can be marked for review when the fix is handed over ("review at the
cohort"). A gate marked for review posts its sheet, asks the person in chat,
and waits for their answer. **Only gate 3 is marked by default**, and only for
changes nobody predicted. Every other gate decides on its own measurement
unless told otherwise.

### 1. The part

Render the defect's part before and after, in the slot the defect names. If
the diff is empty, **stop**: the fix does not touch this part, whatever it
does elsewhere. Also stop if the drawing moved but the defect is still there.

### 2. The cohort

Pick the parts most likely to suffer the same defect. Ways to find them:

- `scripts/part-features.py --have <trait>`: parts built the way the defect's
  part is built.
- Open rows in `tests/goldens/defects.toml` that share the defect's `classes`.
- A cohort script already written for this shape (`scripts/oblique-cohort.py`
  is one). Keep any new one in `scripts/`.

Say why each part was picked. Every part must be no worse than before; it does
not have to be fixed. A part that gets worse stops the fix.

### 3. The goldens

    .venv/bin/python scripts/vet-goldens.py --base origin/main --expect 6589,3941

This renders every case in `tests/goldens/manifest.toml` under the fix's
engine (`--engine`, default occt). `before` comes from a temporary worktree at
`--base`, and `after` from this checkout as it stands, uncommitted edits
included. It runs on the fleet through `onto do`, and the results come back to
`out/vet/<label>/`: a `report.json`, and a `sheet.png` of every case that
moved, unexpected cases first. Only the last 10 runs are kept. `--here` runs
it on this Mac instead, which is for a quick `--only` check.

`--expect` lists the golden parts you predict will move; write it down before
the run. Any other part that moves is marked UNEXPECTED, and the verdict
becomes `review`: post the sheet and ask. A part the person approves counts as
expected. If they reject it, the fix goes back.

The sync ships this checkout's uncommitted edits, which in the shared checkout
can include another session's. The run prints any dirty `brick_icons/` files,
so check that list before trusting the result.

If the fix touches code the naive engine runs, also run
`BRICK_GOLDENS=1 .venv/bin/python -m pytest tests/test_goldens.py`. That gate
is an SVG byte diff, so a failure means "the output moved", not "the output
broke".

### Batching

Several fixes can go through the gates together. When a batch fails a gate,
split it and run each fix through that gate alone to find the one at fault.
The others carry on from the gate where the batch failed.

### Recording it

Each gate's result goes in the defect's `notes` in `tests/goldens/defects.toml`,
in the form existing rows use: the commit, the sheet, and the changed-region
counts. That way the claim survives the conversation.
