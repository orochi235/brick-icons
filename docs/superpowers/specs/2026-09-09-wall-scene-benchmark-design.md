# Benchmarking the wall's paint loop against weasel's scene renderer

**Built and run.** `/bench` in the lab is the harness; the numbers below came off
it on an M2 Max. Read this to find out whether weasel's WebGL2 renderer should
replace `Wall.tsx`'s Canvas2D loop. The short answer is no, not as it stands.

## The answer

Weasel's renderer costs **about 0.007ms per draw command above roughly a
thousand commands, and about 0.0013ms below it** — a five-fold per-command
cliff. So it wins where the wall is already fast and loses where the wall is
slow.

| cell | sheet | commands | canvas2d | scene | |
|---|---|---|---|---|---|
| 8px | 8 | 7,500 | 5.2ms | 65.6ms | 0.08× |
| 12px | 8 | 4,275 | 3.0ms | 26.8ms | 0.11× |
| 16px | 32 | 2,700 | 8.7ms | 19.8ms | 0.44× |
| 24px | 32 | 1,419 | 4.6ms | 10.4ms | 0.44× |
| 32px | 32 | 825 | 2.7ms | 1.1ms | 2.45× |
| 48px | 32 | 414 | 1.4ms | 0.5ms | 2.80× |

Scene times are the better of the two sampling modes at each rung. The dense
low-zoom case — thousands of cells on screen, which is the wall's whole reason
for existing — is where the scene renderer is eight to twelve times slower.

**So the hand-written loop stays.** Not because WebGL2 cannot win here, but
because it does not win today at the sizes that matter, and swapping it in would
make the common case worse.

## What would change the answer

The cliff is in weasel, not in the mapping. Cost per command is flat at ~0.007ms
across 1,419 / 2,700 / 4,275 / 7,500 commands and flat at ~0.0013ms across 414
and 825 — the same texture, the same command shapes, a 5× step between. That
reads as a batch or cache limit being crossed rather than a smooth cost. Finding
and lifting it is a weasel change; if it lands, rerun `/bench` and this
conclusion may invert.

Two things measured along the way that are worth keeping:

**`sampling: 'nearest'` is expensive under minification.** Drawing a 32px tile
into a 16px cell cost 121ms with nearest against 20ms with linear. It is free at
1:1 and above. The wall never minifies much because it swaps sheets by cell size,
so this only bites a consumer that pins one sheet — which the first version of
this harness did, and it produced a wrong answer for two runs.

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

The mapping also declares what it cannot draw. Badges, the kind strip, captions,
the sticker mark, category glyphs and the loose/vector rung are named in
`unsupported`, which forces the rung incomparable rather than fast. That is why
the table stops at 48px: from 56px up a cell wears badges, and reproducing them
is work this measurement did not need.

**Runs interleave, A/B/C/A/B/C.** A sequential run measures the machine's mood;
this repo has filed that twice, at 36× against 18× for one commit and at 0.90×
for the same code on a peer's box.

## Reading it yourself

`npm run dev` in `lab/`, then `/bench`. The page names the GPU it found before
you press Run — a software renderer invalidates the whole table, and headless
WebKit reports no WebGL2 context at all.

## Not done

`<SceneCanvas>`, the full component, is a separate question. It brings the
interaction stack — tools, selection, undo, the gesture dispatcher, hit-testing —
which the wall already has working. Nothing here bears on whether that is worth
adopting; it was deliberately staged behind the paint number, and the paint
number says not yet.
