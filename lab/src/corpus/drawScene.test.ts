import { expect, test } from 'vitest';
import { drawResidue, paintOverlay } from '@lab/corpus/drawScene';
import type { PaintCommand } from '@lab/corpus/paint';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import { toDrawCommands } from '@lab/corpus/toDrawCommands';

/** Records the calls that put ink on the canvas, and nothing else: the point
 *  of every test here is which marks the second half makes, not how it sets up
 *  to make them. */
/** A canvas that counts assignments to `width`, which is what reallocating
 *  its backing store costs. */
function sizedCanvas(width: number, height: number) {
  let w = width;
  let h = height;
  return {
    writes: 0,
    get width() { return w; },
    set width(v: number) { w = v; this.writes++; },
    get height() { return h; },
    set height(v: number) { h = v; },
    style: {} as Record<string, string>,
  };
}

function recorder(canvas: unknown = { width: 100, height: 100, style: {} }) {
  const calls: string[] = [];
  const ctx = new Proxy({} as Record<string, unknown>, {
    get(target, prop: string) {
      if (prop === 'canvas') return canvas;
      if (prop === 'measureText') {
        return () => ({ width: 8, actualBoundingBoxAscent: 6,
                        actualBoundingBoxDescent: 2 });
      }
      if (!(prop in target)) {
        target[prop] = (...args: unknown[]) => {
          if (['fillRect', 'strokeRect', 'drawImage', 'fillText', 'stroke',
               'fill', 'ellipse', 'clearRect'].includes(prop)) {
            calls.push(`${prop}(${args.join(',')})`);
          }
          return undefined;
        };
      }
      return target[prop];
    },
    set() { return true; },
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, calls };
}

const fill = (over: Partial<Extract<PaintCommand, { kind: 'fill' }>> = {}) => ({
  kind: 'fill' as const, dx: 0, dy: 0, dw: 40, dh: 40, fill: '#abc',
  border: null, borderWidth: 0, shape: 'square' as const, slash: false, ...over,
});

const sprite = (over: Partial<Extract<PaintCommand, { kind: 'sprite' }>> = {}) => ({
  kind: 'sprite' as const, dx: 10, dy: 20, dw: 60, dh: 60,
  sx: 4, sy: 8, sw: 32, sh: 32, ground: '#eee', ...over,
});

test('a body weasel already drew is not drawn again', () => {
  const { ctx, calls } = recorder();
  drawResidue(ctx, fill(), null, DEFAULT_PALETTE);
  expect(calls).toEqual([]);
});

test('a plain sprite leaves nothing behind either', () => {
  const { ctx, calls } = recorder();
  drawResidue(ctx, sprite(), null, DEFAULT_PALETTE);
  expect(calls).toEqual([]);
});

test('a slashed cell gets the diagonal and not a second border rect', () => {
  const { ctx, calls } = recorder();
  drawResidue(ctx, fill({ border: '#111', borderWidth: 2, slash: true }),
              null, DEFAULT_PALETTE);
  expect(calls.filter((c) => c.startsWith('strokeRect'))).toEqual([]);
  expect(calls.filter((c) => c.startsWith('stroke('))).toHaveLength(1);
});

test('the category glyph is the second half\'s, since weasel emits no body '
   + 'for a glyphed cell', () => {
  const { ctx, calls } = recorder();
  drawResidue(ctx, fill({ glyph: 'S' }), null, DEFAULT_PALETTE);
  expect(calls.some((c) => c.startsWith('fillText(S'))).toBe(true);
});

test('a captioned sprite draws its caption', () => {
  const { ctx, calls } = recorder();
  drawResidue(ctx, sprite({
    captions: [{ text: '3001', corner: 'bl', ink: '#222' }],
  } as never), null, DEFAULT_PALETTE);
  expect(calls.some((c) => c.startsWith('fillText(3001'))).toBe(true);
});

test('every feature the mapping declines has a branch here -- a command list '
   + 'the two halves share must come out fully painted', () => {
  const cmds: PaintCommand[] = [
    fill({ glyph: 'S' }),
    fill({ mark: 'sticker' } as never),
    fill({ border: '#111', borderWidth: 2, slash: true }),
    sprite({ caret: true }),
    sprite({ captions: [{ text: '3001', corner: 'bl', ink: '#222' }] } as never),
    sprite({ badges: [{ ink: '#000', field: '#fff', corner: 'tr' }] } as never),
    sprite({ strip: [{ ink: '#000', field: '#fff', corner: 'bl' }] } as never),
    { kind: 'image', dx: 0, dy: 0, dw: 40, dh: 40, ground: '#fff',
      image: {} as CanvasImageSource } as PaintCommand,
    { kind: 'label', text: 'Bricks', count: 12, dx: 0, dy: 0, size: 14,
      depth: 0 } as PaintCommand,
  ];
  const { unsupported } = toDrawCommands(cmds, {} as ImageBitmap);
  // Each of these is a real gap in the GL half; the wall is only correct
  // because `drawResidue` covers all of them.
  expect(unsupported.size).toBeGreaterThan(0);
  for (const cmd of cmds) {
    const { ctx, calls } = recorder();
    drawResidue(ctx, cmd, null, DEFAULT_PALETTE);
    expect(calls.length, `${cmd.kind} left nothing on the overlay`)
      .toBeGreaterThan(0);
  }
});

const FRAME = { width: 1200, height: 900, dpr: 1 };

const badged = () => sprite({
  badges: [{ ink: '#000', field: '#fff', corner: 'tr' }],
} as never);

test('the overlay pass clears before it draws, so the frame before it does '
   + 'not ghost through', () => {
  const { ctx, calls } = recorder();
  paintOverlay(ctx, [badged()], FRAME, null, DEFAULT_PALETTE);
  expect(calls[0]).toMatch(/^clearRect/);
  expect(calls.length).toBeGreaterThan(1);
});

test('the overlay keeps its backing store when the frame has not moved', () => {
  const canvas = sizedCanvas(1200, 900);
  const { ctx } = recorder(canvas);
  paintOverlay(ctx, [badged()], FRAME, null, DEFAULT_PALETTE);
  expect(canvas.writes).toBe(0);
});

test('the overlay is resized when the frame has moved', () => {
  const canvas = sizedCanvas(600, 400);
  const { ctx } = recorder(canvas);
  paintOverlay(ctx, [badged()], FRAME, null, DEFAULT_PALETTE);
  expect(canvas.width).toBe(1200);
  expect(canvas.height).toBe(900);
});
