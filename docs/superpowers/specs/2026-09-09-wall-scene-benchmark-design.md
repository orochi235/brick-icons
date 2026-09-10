# Benchmarking the wall's paint loop against weasel's scene renderer

**Built and run.** `/bench` in the lab is the harness; the numbers below came off
it on an M2 Max. Read this to find out whether weasel's WebGL2 renderer should
replace `Wall.tsx`'s Canvas2D loop, and what the wall's hybrid — weasel for the
cell bodies, Canvas2D for the overlays over it — actually costs.

## The answer

The hybrid the wall ships behind `sceneRenderer` is faster than the hand-written
loop at **every** cell size the wall bakes, and no column was withheld for
drift, so within the guard's 12/255 it draws what the loop draws. But the size
of the win depends entirely on whether the cells wear badges: 6–7× where they
do not, **1.14× at 56px where they do.**

Measured against weasel `fee0c98d`, headless Chrome at `deviceScaleFactor` 1,
medians of 7 paints, three passes in one sitting. canvas2d is the same code in
every column, so it is the control.

| cell | commands | canvas2d | scene/linear | hybrid/linear | hybrid |
|---|---|---|---|---|---|
| 8px | 7,500 | 5.2ms | 2.4ms | 3.5ms | 1.5× |
| 12px | 4,275 | 2.7ms | 1.3ms | 1.9ms | 1.4× |
| 16px | 2,700 | 107.2ms | 0.9ms | 1.4ms | 77× |
| 24px | 1,419 | 4.5ms | 0.4ms | 0.7ms | 6.4× |
| 32px | 825 | 2.7ms | 0.3ms | 0.4ms | 6.8× |
| 48px | 414 | 1.4ms | 0.1ms | 0.2ms | 7.0× |
| 56px | 300 | 4.2ms | *withheld* | 3.7ms | 1.14× |

The 16px row is the unexplained canvas2d spike, not a renderer result; see the
hazard below. Below about 1ms the scene column is at the timer's resolution, so
read it as an upper bound rather than a figure.

**Above `BADGE_MIN_PX` the wall's paint is overlay-bound, and the body renderer
stops mattering.** 56px draws 300 cells in 4.2ms where 48px draws 414 in 1.4ms —
the extra 3ms is badges and the kind strip, and the hybrid pays it in full
because it draws them with the same Canvas2D code. Weasel draws the bodies of
that same rung in 0.1ms. So the remaining 3.5ms at 56px is entirely the overlay
pass, which is what the full port below would have to attack; nothing about the
body renderer will move it.

**The two dense rungs cost more than the bare renderer** — 3.5ms against 2.4ms at
8px — because the second canvas is cleared and walked even where no cell wears an
overlay. That is the price of the split, and it is smaller than the win.

Measuring it found one avoidable slice of it: the overlay layer was assigning
`canvas.width` every paint, which reallocates and zeroes the whole surface, on
top of the `clearRect` that follows. About 0.4ms at a 1200×900 frame, and the
Canvas2D control never paid it. `paintOverlay` now only resizes when the frame
actually moved.

**A sha is part of every number here.** Absolutes on this machine drift about a
quarter between sittings, so a figure from another day is not a control. From an
earlier sitting, four builds measured back to back, scene/nearest at 7,500
commands:

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

**Badges, the kind strip and captions still never reach weasel** —
`corpus/toDrawCommands.ts` names them in `unsupported` and emits no draw
command. That no longer stops the rung being measured, because the hybrid draws
them on the layer above and the harness withholds per renderer rather than per
rung; the `scene/*` columns simply go quiet from 56px up. What it costs is the
1.14× at that rung.

**Something makes canvas2d 20–30× slower at the 16px rung, and it is still
unexplained — but it is not what it looked like.** 102.6, 107.0 and 107.2ms
across three passes against `fee0c98d`, and 84.0 to 99.1 in the earlier sitting,
while every neighboring rung on the same sheet stays under 7ms. Four candidates
are now excluded:

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
  `drawPaintCommand`, a bare scene implementation, and a hybrid one.
- `corpus/toDrawCommands.ts` — `PaintCommand[]` to weasel `DrawCommand[]`.
- `bench/harness.ts` — the interleave and the guards.
- `bench/Bench.tsx` — the page.

The scene renderer holds **no scene nodes at all**. An empty `Scene`, the whole
wall as `extraCommands`, and an identity `View`, because `paintCommands` already
emits screen space and a camera on top would transform twice.

**The hybrid column is `corpus/drawScene.ts` itself, not a bench-side copy** —
the same `scenePainter` the `sceneRenderer` param turns on — so the number
belongs to the code that ships. A renderer therefore declares a *stack* of
canvases rather than one, and the fingerprint flattens the stack at full
resolution before downsampling it. Shrinking each layer first and compositing
the small ones is different arithmetic wherever the top layer's alpha varies
across a probe cell, which for an overlay pass is everywhere it draws.

## What the harness refuses to do

**It never reports a ratio for a rung where the two drew different pixels.** A
renderer that skips work is not faster, and this is the failure the whole
exercise is exposed to: WebGL2 silently no-ops without a context, so a renderer
drawing nothing measures as infinitely quick. After the warmup paint of each
rung, every renderer's layer stack is flattened and downsampled to a 32×32
fingerprint in the same task — a WebGL drawing buffer does not survive the task
— and its number is withheld if the result is uniform or drifts more than
12/255 from the control's.

**Withheld per renderer, not per rung.** The hybrid draws a badged cell and the
bare scene renderer does not, so withholding the whole rung on the first gap
would retire the measurement the hybrid exists to take. Only the control
failing takes every column with it.

A column that fails by a point or two is a rasterizer difference and is
expected; one that fails by 40 is a renderer bug, as `d80a7ebc` was.

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

**The full port — badges, the kind strip and captions through weasel — is queued
and unbuilt.** The wall takes the scene renderer for cell bodies only; the
overlays stay on a canvas2d layer stacked above it, because three things in
`draw2d.ts` have no weasel equivalent. Weasel resolves text through an MSDF
atlas where canvas2d uses the platform rasterizer, so caption glyphs may not
agree within this harness's own 12/255 guard. There is no destination-out
composite, so `drawBadge`'s punching marks — the sticker's peel is a hole — want
rebuilding on `GroupDrawCommand.clip`. And placement depends on `measureText`
(`capHalf`, the caption width feeding `stripX`, `badgeWidth`), which weasel does
not expose, so positions would be measured against glyphs it is not drawing.

**What it is now worth is measured: the 56px rung, and everything above it.**
The overlay pass is 3.5 of the hybrid's 3.7ms there, so the port is the only
thing that would move a wall anyone is reading at a legible cell size — and it
is worth 6–7× on that rung if it lands, judging by what weasel does to the
bodies. Below 56px it is worth the 1.1ms the second canvas costs at 7,500
commands, and no more. Not before a spec.

`<SceneCanvas>`, the full component, is a separate question. It brings the
interaction stack — tools, selection, undo, the gesture dispatcher, hit-testing —
which the wall already has working. Nothing here bears on whether that is worth
adopting.
