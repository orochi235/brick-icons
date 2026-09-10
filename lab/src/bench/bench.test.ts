import { beforeEach, expect, test, vi } from 'vitest';
import type { PaintCommand } from '@lab/corpus/paint';
import { toDrawCommands } from '@lab/corpus/toDrawCommands';
import { drift, fingerprint, isBlank, runBench, DRIFT_LIMIT,
         type Rung } from '@lab/bench/harness';
import type { Frame, WallRenderer } from '@lab/bench/renderers';

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
 * whatever the case under test needs. */

let pixels: number[] = [];

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(((kind: string) => {
    if (kind !== '2d') return null;
    return {
      drawImage() {},
      getImageData: () => ({ data: Uint8ClampedArray.from(pixels) }),
    };
  }) as never);
});

function stub(name: string, unsupported: string[] = []): WallRenderer {
  return {
    name,
    canvas: document.createElement('canvas'),
    unsupported: new Set(unsupported),
    paint() {},
  };
}

const RUNG: Rung[] = [{ cellPx: 8, level: 8, commands: [] }];
const FRAME: Frame = { width: 100, height: 100, dpr: 1 };

/** 32x32 probe, four channels, all opaque mid-gray -- a canvas with content. */
const DRAWN = Array.from({ length: 32 * 32 * 4 }, (_, i) => (i % 4 === 3 ? 255 : (i % 97)));

test('withholds a ratio when one renderer cannot draw part of the list', () => {
  pixels = DRAWN;
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b', ['badges'])] });
  expect(r!.speedup).toBeNull();
  expect(r!.incomparable).toContain('badges');
});

test('withholds a ratio when a renderer drew nothing at all', () => {
  pixels = Array.from({ length: 32 * 32 * 4 }, () => 0);
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b')] });
  expect(r!.incomparable).toContain('drew nothing');
  expect(r!.speedup).toBeNull();
});

test('reports a ratio when both drew and neither reported a gap', () => {
  pixels = DRAWN;
  const [r] = runBench({ rungs: RUNG, reps: 1, frame: FRAME,
                         renderersFor: () => [stub('a'), stub('b')] });
  expect(r!.incomparable).toBeNull();
  expect(r!.speedup).not.toBeNull();
});

test('the drift limit is what decides comparability, not a hardcoded pass', () => {
  pixels = DRAWN;
  const a = fingerprint(document.createElement('canvas'))!;
  expect(drift(a, a)).toBeLessThan(DRIFT_LIMIT);
});
