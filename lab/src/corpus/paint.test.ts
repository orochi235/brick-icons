import { expect, it } from 'vitest';
import { fillFor, paintCommands } from '@lab/corpus/paint';
import { DEFAULT_PALETTE as CELL_FILL } from '@lab/corpus/palette';
import type { Cell, SheetManifest } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null,
              overrides: Partial<Cell> = {}): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0,
  error_elsewhere: false, ...overrides,
});

const base = cell('base', 0, null);

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
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  });
  expect(cmd).toMatchObject({ kind: 'sprite', dx: 0, dy: 0, dw: 10, dh: 10,
                              sx: 2, sy: 2, ring: false });
});

it('draws an unrendered cell with nothing known as unknown gray, and no border', () => {
  const [cmd] = paintCommands({
    cells: [cell('b', 1, null)], rects: [rects[1]!], visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  });
  expect(cmd).toEqual({ kind: 'fill', dx: 20, dy: 0, dw: 10, dh: 10,
                        fill: CELL_FILL.unknown.fill, border: null, borderWidth: 0 });
});

it('draws a stale cell as a fill, not as last week’s picture', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-newer')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  });
  expect(cmd!.kind).toBe('fill');
});

it('applies the camera to every command', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: -5, y: -5, scale: { x: 2, y: 2 } }, palette: CELL_FILL, manifest,
  });
  expect(cmd).toMatchObject({ dx: 10, dy: 10, dw: 20, dh: 20 });
});

it('emits nothing for an empty visible set', () => {
  expect(paintCommands({
    cells: [], rects: [], visible: [], cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  })).toEqual([]);
});

it('emits one command per visible index, in the same order', () => {
  const cmds = paintCommands({
    cells: [cell('a', 0, 'sha-a'), cell('b', 1, null)],
    rects, visible: [1, 0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  });
  expect(cmds).toHaveLength(2);
  expect(cmds[0]!.dx).toBe(rects[1]!.x);
  expect(cmds[1]!.dx).toBe(rects[0]!.x);
});

it('falls back to a fill when there is no manifest yet', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  expect(cmd!.kind).toBe('fill');
});

it('draws a whole loose image when one is loaded for the cell', () => {
  const img = {} as HTMLImageElement;
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(cmd).toEqual({ kind: 'image', dx: 0, dy: 0, dw: 10, dh: 10, image: img,
                        ring: false });
});

it('prefers the loose image over the sheet', () => {
  const img = {} as HTMLImageElement;
  const sheetOnly = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map(),
  });
  expect(sheetOnly[0]!.kind).toBe('sprite');
  const withLoose = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(withLoose[0]!.kind).toBe('image');
});

it('rings a drawn cell that has an open defect', () => {
  const img = {} as HTMLImageElement;
  const [withDefect] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { open_defects: 1 })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(withDefect).toMatchObject({ ring: true });
  const [clean] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(clean).toMatchObject({ ring: false });
});

it('flags a part with an open defect in ochre, whatever else is true', () => {
  expect(fillFor({ ...base, open_defects: 1, error: 'GEOSException' }, CELL_FILL))
    .toBe(CELL_FILL.defect);
});

it('separates a part that cannot be drawn from one that timed out', () => {
  expect(fillFor({ ...base, error: 'GEOSException' }, CELL_FILL)).toBe(CELL_FILL.failed);
  expect(fillFor({ ...base, error: 'ProcessDied' }, CELL_FILL)).toBe(CELL_FILL.failed);
  expect(fillFor({ ...base, error: 'TimeoutError' }, CELL_FILL)).toBe(CELL_FILL.timeout);
});

it('mutes a problem that belongs to another permutation', () => {
  expect(fillFor({ ...base, open_defects_elsewhere: 1 }, CELL_FILL))
    .toBe(CELL_FILL.defectElsewhere);
  expect(fillFor({ ...base, error_elsewhere: true }, CELL_FILL))
    .toBe(CELL_FILL.problemElsewhere);
});

it('lets what is wrong here outrank what is wrong elsewhere', () => {
  expect(fillFor({ ...base, error: 'TimeoutError', open_defects_elsewhere: 3 }, CELL_FILL))
    .toBe(CELL_FILL.timeout);
});

it('says nothing is known when nothing is known', () => {
  expect(fillFor(base, CELL_FILL)).toBe(CELL_FILL.unknown);
});

it('emits a fill and border for every problem state, and neither for unknown', () => {
  const states: [Cell, keyof typeof CELL_FILL][] = [
    [{ ...base, open_defects: 1 }, 'defect'],
    [{ ...base, error: 'GEOSException' }, 'failed'],
    [{ ...base, error: 'TimeoutError' }, 'timeout'],
    [{ ...base, open_defects_elsewhere: 1 }, 'defectElsewhere'],
    [{ ...base, error_elsewhere: true }, 'problemElsewhere'],
    [base, 'unknown'],
  ];
  for (const [c, key] of states) {
    const [cmd] = paintCommands({
      cells: [c], rects: [rects[0]!], visible: [0],
      cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
    });
    expect(cmd).toMatchObject({ kind: 'fill', fill: CELL_FILL[key].fill,
                                border: CELL_FILL[key].border });
    if (CELL_FILL[key].border === null) {
      expect((cmd as { borderWidth: number }).borderWidth).toBe(0);
    } else {
      expect((cmd as { borderWidth: number }).borderWidth).toBeGreaterThanOrEqual(1);
    }
  }
});

it('draws a thinner border for a problem elsewhere than for one here', () => {
  const midRect = [{ x: 0, y: 0, w: 20, h: 20 }];
  const [here] = paintCommands({
    cells: [{ ...base, error: 'TimeoutError' }], rects: midRect, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  const [elsewhere] = paintCommands({
    cells: [{ ...base, error_elsewhere: true }], rects: midRect, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  expect((elsewhere as { borderWidth: number }).borderWidth)
    .toBeLessThan((here as { borderWidth: number }).borderWidth);
});

it('scales the border with the drawn cell size, floored at one pixel', () => {
  const tiny = [{ x: 0, y: 0, w: 4, h: 4 }];
  const big = [{ x: 0, y: 0, w: 200, h: 200 }];
  const [smallCmd] = paintCommands({
    cells: [{ ...base, open_defects: 1 }], rects: tiny, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  const [bigCmd] = paintCommands({
    cells: [{ ...base, open_defects: 1 }], rects: big, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  expect((smallCmd as { borderWidth: number }).borderWidth).toBe(1);
  expect((bigCmd as { borderWidth: number }).borderWidth)
    .toBeGreaterThan((smallCmd as { borderWidth: number }).borderWidth);
});
