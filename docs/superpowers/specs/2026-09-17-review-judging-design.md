# Judging a redraw: undo, an honest diff, and a reference panel

For whoever works on the lab's Review page (`/review`). It assumes the review
queue itself, which
[2026-09-17-review-queue-design.md](2026-09-17-review-queue-design.md)
describes: `record_render` logs each displacement, the page shows before,
after and a diff, and a verdict stamps the linked defects.

Three changes, from three faults found while judging on 2026-09-17.

**Status: built.**

## The diff threshold hides whole regressions

`PANEL_THRESHOLD = 64` kept only pixels whose channel delta exceeded 64 of
255. Ten entries in the queue measured zero components under it. Five of them
had changed substantially:

```
part        thr=8 px   comps   fringe%   max delta
50687         39,016       9      0.1%          36
4342          28,343      13      1.0%          13
u9159         18,222       5      0.2%          63
u9252            772       1     31.3%          24
u9331c01         395       8      8.9%         196
47207            246       3     83.7%          60   fringe only
5846              38       0    100.0%          41   fringe only
5847              13       0    100.0%          12   fringe only
5849               0       0         -           0   identical
4629677c           0       0         -           0   identical
```

`56640` is the same class: a shading shift across the whole dome, 77,554
changed pixels, every one of them under the old threshold, and the panel drew
a single speck by the stud.

**The threshold is now 8, and the paint has two tiers keyed on component
size:** a component of at least `PANEL_MIN_PX` pixels paints in full
`PANEL_COLOR`, anything smaller in `PANEL_FAINT`, a 35% tint of it. The
caption carries the component count and the changed-pixel count, so a change
can never read as zero.

**Do not tier on amplitude.** It is the signal that fails on exactly this
class: 4342's entire regression peaks at a delta of 13, indistinguishable
from antialias fringe by amplitude alone, and 56640's sits at 23. Colored by
amplitude, every hidden regression above paints in the faintest tier and
reads as nothing. Component size separates them cleanly — the real changes
above are 99%+ bulk, the fringe-only ones 84–100% fringe.

**Two tiers, not three.** Pooled over 19 pairs, 2,444 components carrying
398,884 changed pixels: components of at least 12px are 9.0% of the
components and 98.9% of the ink; at least 200px, 3.8% and 96.9%. A middle
tier at 12–200 covers 126 components carrying 2% of the pixels and would be
invisible whatever color it got. The break at `PANEL_MIN_PX` is where the
distribution actually divides.

`scripts/_sheet.py` carries its own `DIFF_THRESHOLD` and moves in step, or a
diff panel on the wall stops agreeing with the one the lab serves.

Connected components are found by union-find over the 4-neighbor edges, in
numpy. `scipy.ndimage.label` would be the obvious call and is not available:
scipy is declared only under the `census` extra, and package code that
imports it dies on a node provisioned without that extra — the failure
`pyproject.toml` already carries a comment about.

## A verdict cannot be taken back

A misjudgement was permanent. The verdict wrote `status`, `checked[source]`
and an appended note line onto every linked defect, and the page dropped the
card.

**`record_judged` now records what it is about to overwrite.** The `judged`
line gains `restore`: per defect id, the `status`, `checked` and `notes` held
before the write. Undo writes those three fields back verbatim — no string
surgery on the notes, no guessing at a previous sha.

**Undo appends, it does not delete.** `review.jsonl` stays append-only, so
undo writes a `{"kind": "unjudged", "id": …}` line and `review.fold` learns
that kind, clearing `judged` back to `None`. A replay rebuilds the same
state. `POST /api/review/{eid}/undo` clears the verdict columns on the
`review` row, restores each defect through `defects.update`, mirrors each to
`corpus.db`, and returns the refreshed entry.

A `judged` line written before this change has no `restore`. Undo on one
falls back to: status to `open`, drop `checked[source]`, leave the notes
alone — and says so in the response, because the previous sha is genuinely
not recoverable.

On the page, the judged line grows an `undo` button and `u` undoes the
focused card. Judging no longer removes the card from the list: it stays in
place wearing its `data-verdict` for the rest of the session, so undo is
reachable without ticking "show judged".

## Nothing on the card says what the part should look like

Before and after answer "did this change", never "which one is right". The
LDView reference answers it: on `56640` it shows the dome clearly lighter
than the flange under one smooth highlight, which `before` matches and
`after` does not.

`GET /api/review/{eid}/reference.png` renders through the existing
`reference.render_reference` and streams the cached PNG. One hop, so the card
is an `<img loading="lazy">` and offscreen cards never spawn an LDView
subprocess.

The review row records no angle. Corpus renders are all drawn at the config
default, so the panel uses `load_config(root).angle` and captions itself
`reference · <angle>`; without that, the first part drawn at another pose
shows a reference that silently does not match it.

It is ground truth for structure, not pixels — a shaded color render against
line art — so it never feeds the diff. When LDView is missing or errors the
panel is a captioned empty tile and the card still works.
