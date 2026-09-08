# brick-icons

Renders LDraw parts as line-drawing icons. Three engines behind `--engine`:
`naive` (z-buffer, the reference), `occt` (OpenCASCADE hidden-line removal),
and `cadquery` (cadquery's stock SVG exporter, for comparison only).

## LDraw parts are defective, and the engine must not care

Library geometry is cracked, unwelded and inconsistently wound as a matter of
course — that is what `repair.py` exists for. **A rule that assumes a sound
shape is wrong by construction**, and will pass on the parts you tested and
fail on the next defect you have not met. Tried and failed: G1 continuity
tagging (needs two faces per edge), treating a curved free boundary as a rim
(reads a crack as a feature), "both adjacent faces are curved" (assumes a wall
is one surface).

What works asks only whether something was **declared** — type-2 lines, `edge`
primitives, type-5 conditional lines, junctions between exact surfaces. A crack
declares nothing, so it contributes nothing. Hence: don't invest in closing
cracks, invest in rules that survive them. Parts render correctly today with
more than half their edges unpaired.

Never infer geometry from a dihedral angle across *tessellation* — that draws
every facet boundary, the failure the OCCT engine exists to avoid. Between two
exact analytic surfaces it is measurable and safe; measure first
(`scripts/measure-crease-angles.py`).

## Part numbering, and what it does and does not tell you

Counts are from the vendored library, 24,591 part files.

| form | count | meaning |
|---|---|---|
| `3001` | 7541 | base part |
| `3068b` | 3268 | mould variant — **or** a sticker-sheet item (2379 of these) |
| `3068bp00`, `14769p0a` | 8639 | printed (8176 described `Pattern`) |
| `3069bpr0001` | 20 | printed, newer convention |
| `...c01` | 2033 | composite/assembly |
| `...d01` | 899 | sticker (863 of them) |
| `u9…` | 1164 | unofficial |

**Identify printed parts by the description line** (`Pattern`/`Sticker` in line
1 of the `.dat`), not the id: `^\d{3,}p\d+$` catches 3254 of 13081, a plain
letter suffix is ambiguous, and 132 bare-numeric ids are patterned. The id is
fine as a fast path, never as the authority.

**Strip a printed part's decoration and you should be left with its base part** —
`4740p03` → `4740`, and the base exists for 8615 of 8639. That is a free oracle
for the decal-stripping stage over thousands of parts with nothing to label.

## Printed parts and stickers are in scope

Both were excluded once and are not any more — the decal work landed, and
`scripts/census-scope.py` takes every non-obsolete part. occt errors on 397 of
12,429 printed parts and 6 of 2,701 stickers; naive still errors on 117
stickers. **So a decorated part that fails under naive is the known fault**;
reproduce it under occt before treating it as a finding.

`db.OUT_OF_SCOPE_CATEGORIES` is down to `|`, LDraw's mark for a part nobody at
LEGO made — third-party electronics and wheels that fit LEGO.

## Look at renders; never describe them from memory

- **A small pixel diff is not agreement.** Antialias fringe scatters into
  hundreds of tiny components; a real defect is a handful of chunky ones.
  Component-count the diff instead of eyeballing a thumbnail.
- **A silent `[]` is not "unrepresentable".** `occt_faces` returns `[]` both for
  "no exact surface exists" and "my tolerance was too tight", and two tolerance
  constants once deleted whole walls with no error anywhere. Remove the
  `except` and look before believing it.
- **An image on the wall labels what VARIES between its panels.** Several
  sessions post to one zone, so a sheet arrives with no conversation around it
  and has to answer "what am I looking at" by itself. Give it a title line, and
  label each panel with the thing that changed -- `before` / `after`, `step 15`
  / `step 25`, `naive` / `occt`. Repeating the part id and config under both
  halves of a pair, which is what `fixB-inkab` did, names everything except the
  one difference the pair exists to show: the reader is left guessing which
  side is the new one, and a guess about panel order turns a regression report
  into a maybe.

## The lab must not fork the CLI

`brick_icons/lab/` derives its config schema from `cli.build_parser()` and runs
renders through `_config_from_args` + `process_one`. Never add a lab-side
parameter table, and never re-implement a render path there: a parameter the
lab knows and the CLI does not is a bug by construction, and
`tests/test_lab_schema.py` fails on it.

## Long jobs go through `onto`, and they go to another machine

Anything running longer than a few minutes is launched with `onto run`, never as
a backgrounded shell command. **Send it to a remote node.** This Mac runs the
editor, the browsers, the lab servers and several Claude sessions at once, and
it is the only machine whose slowness anyone feels; the fleet exists so it does
not also grind through renders. `onto status` names a node with free cores, or
`--any` picks one.

    onto run --detach --timeout 4h --task thumb-bake --in brick-icons \
      --env PATH=/opt/homebrew/bin:/usr/bin:/bin \
      --out out/thumbs --to out/thumbs \
      msb-uai -- .venv/bin/python scripts/bake-thumbs.py

This machine is enrolled as `orochi`, so `--dir "$PWD"` can run a job in place
with no sync and no fetch. **That is the exception and it needs a reason** —
the job needs this checkout's uncommitted state, or it is minutes rather than
tens of them. "Shipping the inputs would take a while" is not one: the sync is
paid once and the node keeps what it got, while every local run is paid again
out of the machine you are working on. Ship it first and let it copy in the
background — deciding is what costs the hour, not the transfer.

`--task` is the identity and it is the point. Several Claude sessions share this
working directory and cannot see each other's background processes; two once ran
`bake-thumbs.py` at the same time, writing the same thumbnails and racing on the
same `sheet-*.png`. Relaunching under a task name continues that task instead of
forking a rival, and `onto jobs` answers "is this already running?" for everyone.

Two traps. The agent's PATH is not your shell's, so pass `--env PATH=...`
covering everything the job shells out to — a missing `resvg` fails every part
in about a second, silently. And check the deadline `onto run` prints: the agent
clamps to 30 minutes unless it was installed with `-max-job-time`, and a
reinstall reverts that.
