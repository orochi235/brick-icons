# Benchmarking the wall's paint loop against weasel's scene renderer

**Built and run.** `/bench` in the lab is the harness; the numbers below came off
it on an M2 Max. Read this to find out whether weasel's WebGL2 renderer should
replace `Wall.tsx`'s Canvas2D loop. The answer changed once weasel started
batching: it is now yes, pending the badge gap below.

## The answer

Weasel's renderer is faster than the hand-written loop at **every** cell size the
wall bakes, from 1.5× in the densest case to about 8× in the middle of the range,
and it draws the same pixels.

Measured against weasel `514cbc0e` (which carries the batch work merged as
`f0a47538`). canvas2d is the same code in every column, so it is the control.
The table holds at `deviceScaleFactor` 2 as well as 1: both renderers move by
under 0.5ms on every rung, so a retina window does not change the verdict.

| cell | commands | canvas2d | scene/nearest | |
|---|---|---|---|---|
| 8px | 7,500 | 5.2ms | 3.4ms | 1.5× |
| 12px | 4,275 | 2.9ms | 1.7ms | 1.7× |
| 16px | 2,700 | 8.9ms | 1.1ms | 8.0× |
| 24px | 1,419 | 4.5ms | 0.6ms | 7.5× |
| 32px | 825 | 2.6ms | 0.3ms | 8.7× |
| 48px | 414 | 1.4ms | 0.2ms | 7.0× |

The 16px canvas2d figure is the one from the unbatched runs in the same sitting;
see the hazard below.

**A sha is part of every number here.** Absolutes on this machine drift about a
quarter between sittings, so a figure from another day is not a control. Four
builds, measured back to back, scene/nearest at 7,500 commands:

| weasel build | | 7,500 commands | pixels |
|---|---|---|---|
| `@weasel-js/core` 1.4.0 | installed release | 76.2ms | agree |
| `89276eea` | before the batch work | 91.9ms | agree |
| `d80a7ebc` | batch, before the fix | 2.8ms | **disagree, 40.6 to 84.8** |
| `514cbc0e` | batch, after the fix | 3.4ms | agree, 0.9 to 1.9 |

`d80a7ebc` was fast for the wrong reason: `flushBatch` bound the run's adopted
bitmap, so every solid sampled it at (0.5, 0.5) and the wall came back a flat
olive. The harness caught it and withheld the ratio, which is what it is for.
`f0a47538` gives each batch vertex its own texture slot and the pixels come back.

## What is still in the way

**Badges, the kind strip and captions have never reached this renderer.**
`bench/toDrawCommands.ts` names them in `unsupported` and emits no draw command,
so any rung whose cells wear them is withheld rather than measured — which is why
the table stops at 48px. Adopting the scene renderer means writing those, and
they are the wall's, not weasel's.

**Something makes canvas2d 20–30× slower at the 16px rung, and it is still
unexplained — but it is not what it looked like.** 84.0, 89.6 and 99.1ms across
three passes of one page against `514cbc0e`, while every neighboring rung on the
same sheet stays under 7ms. Four candidates are now excluded:

- **Not minification.** 2,700 tiles drawn from the 32px sheet on a fresh page
  cost 7.4ms into 16px cells against 6.8ms into 32px — a 2:1 reduction is free.
- **Not `imageSmoothingEnabled`.** Same test with smoothing off: 7.8ms.
- **Not the sheet's first touch.** 16px is the first rung to draw the 5652²
  level-32 sheet, but the spike survives three consecutive passes in one page.
- **Not dpr.** 151.1ms at `deviceScaleFactor` 1 against 95.0ms at 2, and every
  other rung moves by under 0.5ms between the two.

What has not been tested is the co-tenancy the earlier note guessed at: whether
the spike survives with the GL renderers absent from the page. That needs the
rung order changed or the scene renderers dropped, and it is the next thing to
try.

## Two things measured along the way

**On our atlas, `sampling: 'nearest'` costs up to 8x linear, and the gap tracks
minification.** From the 1.4.0 control, scene/nearest over scene/linear by rung:
16px 8.11, 24px 5.98, 32px 1.08, 48px 1.14. The sheet holds 32px tiles, so those
are 2:1, 1.33:1, 1:1 and magnifying — the gap vanishes exactly at 1:1, and on the
small level-8 sheet it inverts to the ordinary expectation. That is backwards
from the filter arithmetic, and it is a property of how big our sheet is:
**5652 x 5652, which is 122 MB resident RGBA**, not the 12 MB this repo had been
quoting, which is the compressed webp over the wire. Weasel's own atlases are
about 3 MB and their spec sees none of this. Weasel has since fixed a redundant
`MAG_FILTER` write found while chasing it (`fee0c98d`) and says it does not
explain the 8x, so do not record it as solved; if we ever shrink the sheet or add
mipmaps, this is the number that should move.

The wall never minifies much because it swaps sheets by cell size, so this only
bites a consumer that pins one sheet — which the first version of this harness
did, and it produced a wrong answer for two runs.

**A group per cell is not the cost.** Wrapping every sprite in a
`GroupDrawCommand` versus emitting flat changed nothing measurable. The node-per-
cell worry that ruled out windease does not apply to draw commands.

## How it is built

`paintCommands()` already returns `PaintCommand[]` and was the only seam needed.
`Wall.tsx`'s executor moved to `corpus/draw2d.ts` unchanged, so both renderers
consume the identical list:

- `bench/renderers.ts` — `WallRenderer`, with a Canvas2D implementation wrapping
  `drawPaintCommand` and a scene implementation.
- `bench/toDrawCommands.ts` — `PaintCommand[]` to weasel `DrawCommand[]`.
- `bench/harness.ts` — the interleave and the guards.
- `bench/Bench.tsx` — the page.

The scene renderer holds **no scene nodes at all**. An empty `Scene`, the whole
wall as `extraCommands`, and an identity `View`, because `paintCommands` already
emits screen space and a camera on top would transform twice.

## What the harness refuses to do

**It never reports a ratio for a rung where the two drew different pixels.** A
renderer that skips work is not faster, and this is the failure the whole
exercise is exposed to: WebGL2 silently no-ops without a context, so a renderer
drawing nothing measures as infinitely quick. After the warmup paint of each
rung, every canvas is downsampled to a 32×32 fingerprint in the same task — a
WebGL drawing buffer does not survive the task — and the rung is marked
incomparable if any canvas is uniform or drifts more than 12/255 from the first.

A rung that fails by a point or two is the badge gap above and is expected; a
rung that fails by 40 is a renderer bug, as `d80a7ebc` was.

## Reading it yourself

`npm run dev` in `lab/`, then `/bench`. To measure an unreleased weasel, build
its `packages/core` and run `WEASEL_SRC=~/src/weasel npm run dev`; the vite
alias points at `dist`, so what runs is what a release would ship. To measure
several shas in one sitting without leaving the weasel checkout detached, build
each and copy its `dist` to
`~/src/weasel/node_modules/.bench-snapshots/<sha>/packages/core/dist` — module
resolution still walks up to weasel's own `node_modules`, and `WEASEL_SRC` takes
the snapshot directory.

The page names the GPU it found before you press Run — a software renderer
invalidates the whole table, and headless WebKit reports no WebGL2 context at
all. Headless Chrome does: it reports ANGLE Metal on the M2 Max, at `dpr` 1
rather than the 2 a real window gets.

## Not done

`<SceneCanvas>`, the full component, is a separate question. It brings the
interaction stack — tools, selection, undo, the gesture dispatcher, hit-testing —
which the wall already has working. Nothing here bears on whether that is worth
adopting.
