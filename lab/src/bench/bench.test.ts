import { beforeEach, expect, test, vi } from 'vitest';
import type { PaintCommand } from '@lab/corpus/paint';
import { toDrawCommands } from '@lab/corpus/toDrawCommands';
import { drift, fingerprint, isBlank, runBench, DRIFT_LIMIT,
         type Rung } from '@lab/bench/harness';
import { hybridRenderer, type Frame, type WallRenderer } from '@lab/bench/renderers';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';

const SHEET = {} as ImageBitmap;

const sprite = (over: Partial<Extract<PaintCommand, { kind: 'sprite' }>> = {}) => ({
  kind: 'sprite' as const, dx: 10, dy: 20, dw: 30, dh: 30,
  sx: 4, sy: 8, sw: 32, sh: 32, ground: '#eee', ...over,
});

test('a sprite becomes a ground fill and an atlas blit, in that order', () => {
  const { commands, unsupported } = toDrawCommands([sprite()], SHEET);
  expect(unsupported.size).toBe(0);
  expect(commands.map((c) => c.kind)).toEqual(['path', 'image']);
});

test('an opaque sprite is emitted flat -- a group per cell is a state change '
   + 'per cell, and would be charged to the renderer', () => {
  const { commands } = toDrawCommands([sprite()], SHEET);
  expect(commands.some((c) => c.kind === 'group')).toBe(false);
});

test('a dimmed sprite gets the group its alpha needs', () => {
  const { commands } = toDrawCommands([sprite({ alpha: 0.4 })], SHEET);
  expect(commands).toHaveLength(1);
  expect(commands[0]!.kind).toBe('group');
  expect((commands[0] as { alpha?: number }).alpha).toBe(0.4);
});

test('the atlas blit carries the tile sub-rect and samples nearest', () => {
  const { commands } = toDrawCommands([sprite()], SHEET);
  const img = commands[1] as unknown as Record<string, unknown>;
  // Linear sampling reaches past `source`, which would bleed the neighboring
  // tile into every cell edge.
  expect(img.sampling).toBe('nearest');
  expect(img.source).toEqual({ x: 4, y: 8, w: 32, h: 32 });
  expect([img.x, img.y, img.w, img.h]).toEqual([10, 20, 30, 30]);
});

test('a sprite with no sheet draws nothing rather than a bare ground', () => {
  const { commands } = toDrawCommands([sprite()], null);
  expect(commands).toHaveLength(0);
});

test('badges are reported unsupported, not quietly skipped', () => {
  const { unsupported } = toDrawCommands(
    [sprite({ badges: [{ ink: '#000', field: '#fff', corner: 'tr' }] as never })],
    SHEET);
  expect([...unsupported]).toContain('badges');
});

test('a plain fill cell becomes one path', () => {
  const cmd: PaintCommand = {
    kind: 'fill', dx: 0, dy: 0, dw: 10, dh: 10, fill: '#abc',
    border: null, borderWidth: 0, shape: 'square', slash: false,
  };
  const { commands, unsupported } = toDrawCommands([cmd], SHEET);
  expect(commands).toHaveLength(1);
  expect(commands[0]!.kind).toBe('path');
  expect(unsupported.size).toBe(0);
});

test('a bordered fill adds a stroked rect inset by half the width', () => {
  const cmd: PaintCommand = {
    kind: 'fill', dx: 0, dy: 0, dw: 10, dh: 10, fill: '#abc',
    border: '#111', borderWidth: 2, shape: 'square', slash: false,
  };
  const { commands } = toDrawCommands([cmd], SHEET);
  expect(commands).toHaveLength(2);
  expect((commands[1] as { stroke?: { width: number } }).stroke?.width).toBe(2);
});

test('drift is zero for identical fingerprints and grows with difference', () => {
  expect(drift([1, 2, 3], [1, 2, 3])).toBe(0);
  expect(drift([0, 0], [10, 20])).toBe(15);
});

test('a flat fingerprint reads as blank', () => {
  expect(isBlank([0, 0, 0, 0])).toBe(true);
  expect(isBlank([0, 0, 1, 0])).toBe(false);
  expect(isBlank(null)).toBe(true);
});

/* The harness's own guards, driven with stub renderers so the pixels are
 * whatever the case under test needs.
 *
 * jsdom has no canvas, so `getContext('2d')` is faked with a buffer that
 * composites source-over at 1:1 -- enough to hold a layer stack in the order
 * it was drawn, which is the thing the fingerprint has to get right. */

const PROBE_LEN = 32 * 32 * 4;

interface Painted extends HTMLCanvasElement { __px?: number[] | null }

/** A canvas carrying the pixels a paint would have left on it. */
function layer(px: number[] | null): HTMLCanvasElement {
  const c = document.createElement('canvas') as Painted;
  c.__px = px;
  return c;
}

let pixels: number[] = [];

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
    (function (this: Painted, kind: string) {
      if (kind !== '2d') return null;
      // The buffer hangs off the element, not the context, so a canvas drawn
      // into and then drawn FROM carries what landed on it -- which is what
      // compositing a layer stack through a scratch canvas does.
      this.__px ??= new Array<number>(PROBE_LEN).fill(0);
      const buf = this.__px;
      return {
        drawImage(src: Painted) {
          const px = src.__px;
          if (!px) return;
          for (let i = 0; i < buf.length; i += 4) {
            const a = px[i + 3]! / 255;
            for (let k = 0; k < 3; k++) buf[i + k] = px[i + k]! * a + buf[i + k]! * (1 - a);
            buf[i + 3] = 255 * a + buf[i + 3]! * (1 - a);
          }
        },
        getImageData: () => ({ data: Uint8ClampedArray.from(buf) }),
      };
    }) as never);
});

function stub(name: string, unsupported: string[] = []): WallRenderer {
  return {
    name,
    layers: [layer(pixels)],
    unsupported: new Set(unsupported),
    paint() {},
  };
}

const RUNG: Rung[] = [{ cellPx: 8, level: 8, commands: [] }];
const FRAME: Frame = { width: 100, height: 100, dpr: 1 };

/** 32x32 probe, four channels, all opaque mid-gray -- a canvas with content. */
const DRAWN = Array.from({ length: 32 * 32 * 4 }, (_, i) => (i % 4 === 3 ? 255 : (i % 97)));

test('withholds a renderer that cannot draw part of the list', () => {
  pixels = DRAWN;
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b', ['badges'])] });
  expect(r!.timings[1]!.withheld).toContain('badges');
});

test('withholds a renderer that drew nothing at all', () => {
  pixels = Array.from({ length: 32 * 32 * 4 }, () => 0);
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b')] });
  expect(r!.timings[1]!.withheld).toContain('drew nothing');
});

test('withholds nothing when both drew and neither reported a gap', () => {
  pixels = DRAWN;
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b')] });
  expect(r!.timings.map((t) => t.withheld)).toEqual([null, null]);
});

test('the drift limit is what decides comparability, not a hardcoded pass', () => {
  const a = fingerprint([layer(DRAWN)])!;
  expect(drift(a, a)).toBeLessThan(DRIFT_LIMIT);
});

/** Transparent: what the hybrid's overlay layer is everywhere it draws no
 *  badge, and what its GL layer is if the context is lost. */
const CLEAR = Array.from({ length: PROBE_LEN }, () => 0);

/** Ink in the top-left quarter and transparent elsewhere -- an overlay pass,
 *  which covers a fraction of the frame rather than all of it. */
const INK = Array.from({ length: PROBE_LEN }, (_, i) => {
  const px = i >> 2;
  const on = (px >> 5) < 16 && (px % 32) < 16;
  return on ? (i % 4 === 3 ? 255 : 240) : 0;
});

test('a renderer fingerprints its layers stacked, so a drawn overlay over a '
   + 'blank body does not read as blank', () => {
  expect(isBlank(fingerprint([layer(CLEAR), layer(INK)]))).toBe(false);
});

test('an overlay layer that stopped drawing moves the fingerprint past the '
   + 'drift limit', () => {
  const both = fingerprint([layer(DRAWN), layer(INK)])!;
  const bodyOnly = fingerprint([layer(DRAWN)])!;
  expect(drift(both, bodyOnly)).toBeGreaterThan(DRIFT_LIMIT);
});

test('a gap in one renderer leaves the renderers that drew everything comparable', () => {
  pixels = DRAWN;
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b', ['badges']),
                                              stub('c')] });
  expect(r!.timings[1]!.withheld).toContain('badges');
  expect(r!.timings[2]!.withheld).toBeNull();
});

test('the hybrid presents its GL layer under its overlay -- the order the '
   + 'fingerprint flattens them in', () => {
  const gl = layer(null);
  const overlay = layer(null);
  const r = hybridRenderer(gl, overlay, { bitmap: null, img: null }, DEFAULT_PALETTE);
  expect(r.layers).toEqual([gl, overlay]);
});
