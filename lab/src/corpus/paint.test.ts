import { expect, it } from 'vitest';
import { paintCommands, STATUS_FILL } from '@lab/corpus/paint';
import type { Cell, SheetManifest } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null,
              status = 'unreviewed'): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status, sha, made_at: null, extra_d99: null, secs: null, error: null,
});

const manifest: SheetManifest = {
  level: 32, gutter: 2, pitch: 36, cols: 2, rows: 2, count: 4, size: 72,
  baked: { a: 'sha-a' },
};

const rects = [
  { x: 0, y: 0, w: 10, h: 10 },
  { x: 20, y: 0, w: 10, h: 10 },
];

it('draws a baked cell from the sheet', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd).toMatchObject({ kind: 'sprite', dx: 0, dy: 0, dw: 10, dh: 10,
                              sx: 2, sy: 2 });
});

it('draws an unrendered cell as its status color', () => {
  const [cmd] = paintCommands({
    cells: [cell('b', 1, null, 'broken')], rects: [rects[1]!], visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd).toEqual({ kind: 'fill', dx: 20, dy: 0, dw: 10, dh: 10,
                        fill: STATUS_FILL.broken });
});

it('draws a stale cell as a fill, not as last week’s picture', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-newer')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmd!.kind).toBe('fill');
});

it('applies the camera to every command', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: -5, y: -5, scale: 2 }, manifest,
  });
  expect(cmd).toMatchObject({ dx: 10, dy: 10, dw: 20, dh: 20 });
});

it('emits nothing for an empty visible set', () => {
  expect(paintCommands({
    cells: [], rects: [], visible: [], cam: { x: 0, y: 0, scale: 1 }, manifest,
  })).toEqual([]);
});

it('emits one command per visible index, in the same order', () => {
  const cmds = paintCommands({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1, null)],
    rects, visible: [1, 0],
    cam: { x: 0, y: 0, scale: 1 }, manifest,
  });
  expect(cmds).toHaveLength(2);
  expect(cmds[0]!.dx).toBe(rects[1]!.x);
  expect(cmds[1]!.dx).toBe(rects[0]!.x);
});

it('falls back to a fill when there is no manifest yet', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest: null,
  });
  expect(cmd!.kind).toBe('fill');
});

it('draws a whole loose image when one is loaded for the cell', () => {
  const img = {} as HTMLImageElement;
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map([['a', img]]),
  });
  expect(cmd).toEqual({ kind: 'image', dx: 0, dy: 0, dw: 10, dh: 10, image: img });
});

it('prefers the loose image over the sheet', () => {
  const img = {} as HTMLImageElement;
  const sheetOnly = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map(),
  });
  expect(sheetOnly[0]!.kind).toBe('sprite');
  const withLoose = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: 1 }, manifest, loose: new Map([['a', img]]),
  });
  expect(withLoose[0]!.kind).toBe('image');
});
