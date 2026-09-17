# Handoff: verifying open defects against the drawing at HEAD

Written 2026-09-16, overnight. For whoever picks up defect triage next. On
`main` in the shared checkout; nothing here is committed, and
`tests/goldens/defects.toml` is the only repository file this thread changed
besides three new scripts.

## What this thread was

Every render in the corpus is behind at least one drawing commit, so a defect
filed in September was filed against a picture nobody draws any more. This
pass redraws the part at HEAD, puts it beside the browser reference, and says
whether the complaint is still true. 47 rows closed, 30 given a measured note,
1 new row filed. `defects.toml` went 208 open / 38 fixed to 162 / 85.

Three render rounds were launched alongside it and are still running at the
time of writing: `slot-occt-refresh` on studio (7,379 occt parts redrawn at the
current engine), and `slot-white-occt-stale` on keiei plus
`slot-silhouette-occt-stale` on msb-uai (the errored parts whose last attempt
predates the engine change). The retry rounds recover well -- white-occt and
silhouette-occt had each gained about a hundred parts within twenty minutes.

## The two things worth knowing before you carry on

**A drawing that did not change is not a defect that still stands.** The first
filter tried here was `scripts/defect-drift.py`: draw the part at the filed-era
build and at HEAD, component-count the difference, and only look at the ones
that moved. It is the wrong filter and it would have thrown away every closure
in this pass -- all nine `mirrored` decal rows came back pixel-identical
between 44aeaf1 and HEAD, and not one of them reproduced. A defect is filed
against the CORPUS render the lab was showing, which is older than any build
you can name and is overwritten the next time the slot is filled. The script
is kept, because "did this engine change move this part" is a real question;
its docstring now says what it does not answer.

**Judge "extra ink" at full size, never in a contact sheet.** A 300 px panel
hid the seam round 11833's side wall completely, and three `missing` rows
looked clean at that size while the edge oracle found a real gap in each
(38583, 2947bc01, 3813). Two tools, and the split between them is sharp:

- `scripts/edge-gaps-now.py` draws a part at HEAD and scores it against the
  edges its `.dat` declares. A zero refutes "missing lines" and refutes
  nothing else -- it is blind to extra ink, to shading, to a surface with no
  edge to mark it, and to a part that declares no edges at all, which scores
  0 of 0 px and means only that the question was not asked.
- `scripts/defect-sheet.py` draws one row per defect: the browser reference,
  optionally the drawing at `--before <rev>`, and the drawing at HEAD. It is
  the only thing that answers a shading, decal or extra-ink complaint.

## What is still open that this pass measured

Six rows are down to a named number rather than a guess: 7610 (3 gaps, 184.0
of 2259.5 px declared), 61482 (5 gaps, 136.0 of 2517.0, and its two rows are
one fault), 93091 (5 gaps, 91.0 of 2496.5), 54568, 10830, 3813, 2947bc01 and
38583 (one gap each, 10-28 px). 7610 and 61482 are where a missing-edge fix
would show first.

Four rows shrank to half their title: 3626bp8j is now the temple mark alone,
6148328s the sharp corners alone, 30137's complaint is answered and its face
carries a light wedge instead (filed as `30137-light-wedge-across-ribs`), and
6288456b is not mirrored at all -- the decal slot gives that sticker a
landscape canvas where the part is authored 1.8 by 2.8, so the aspect is
transposed. That row should be read against `decal`, not `occt`.

005048b draws the flag's canton as flat blue with none of its ~50 stars, and
the edge oracle cannot see it: the part declares no type-2 edges.

## Traps

`defects.toml` is shared. A peer session was closing occt geometry rows in it
at the same time as this pass, so it is edited in place -- status flipped and a
note spliced into the record -- rather than rewritten through
`lab.defects.save()`, which would reformat their hand edits into this diff.
Keep doing that, and commit by naming the path.

**A refresh round ingests nothing without `ingest-watch.py --overwrite`.** The
watcher skips any part the slot already holds, so `slot-occt-refresh` fetched
700 drawings home and left `renders` untouched; the watcher's own log looked
healthy throughout. Restarting it with `--overwrite` took the backlog in one
pass. This is now written into the `render-corpus-batch` skill at step 6b.

`defect-sheet.py` draws into `--tmp`, one directory per (part, slot). An
earlier version shared one directory and its glob took whichever slot had
drawn the part first, so a sheet titled `occt` came back full of decal panels
with nothing saying so. If a panel looks like the wrong slot, that is why.
