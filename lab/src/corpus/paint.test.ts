import { describe, expect, it } from 'vitest';
import { badgeGeometry, badgesFor, captionsFor, CAPTION_ON_FILL, cellState, fillFor,
  paintCommands, PROPERTY_FIELD, stripFor, tally, THUMB_GROUND } from '@lab/corpus/paint';
import { CELL_STATES, DEFAULT_PALETTE as CELL_FILL, type CellState } from '@lab/corpus/palette';
import type { Band } from '@lab/corpus/layout';
import { tintFor } from '@lab/corpus/tint';
import type { Cell, SheetManifest } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null,
              overrides: Partial<Cell> = {}): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false, base: true, out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0, accepted_defects: 0,
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
                              sx: 2, sy: 2, border: null });
});

it('draws an unrendered cell with nothing known as unknown gray, and no border', () => {
  const [cmd] = paintCommands({
    cells: [cell('b', 1, null)], rects: [rects[1]!], visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
  });
  expect(cmd).toEqual({ kind: 'fill', dx: 20, dy: 0, dw: 10, dh: 10,
                        fill: CELL_FILL.unknown.fill, border: null, borderWidth: 0,
                        shape: 'square', slash: false, glyph: undefined,
                        captions: [] });
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
                        ground: THUMB_GROUND, translucent: false, border: null,
                        borderWidth: 0, badges: [], strip: [], captions: [],
                        wash: undefined });
});

it('grounds a vector cell on what the thumbnails were baked against', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    vector: new Map([['a', {} as CanvasImageSource]]),
  });
  expect(cmd).toMatchObject({ kind: 'image', ground: '#ffffff' });
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

it('prefers a rasterized vector over the loose image', () => {
  const loose = {} as HTMLImageElement;
  const vectored = {} as CanvasImageSource;
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    loose: new Map([['a', loose]]), vector: new Map([['a', vectored]]),
  });
  expect(cmd).toMatchObject({ kind: 'image', image: vectored });
});

it('frames a drawn cell in its state color, defect or trouble elsewhere', () => {
  const img = {} as HTMLImageElement;
  const [withDefect] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { open_defects: 1 })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(withDefect).toMatchObject({ border: CELL_FILL.defect.border });
  const [clean] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, loose: new Map([['a', img]]),
  });
  expect(clean).toMatchObject({ border: null, borderWidth: 0 });
  const [elsewhere] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { error_elsewhere: true })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    loose: new Map([['a', img]]),
  });
  expect(elsewhere).toMatchObject({ border: CELL_FILL.problemElsewhere.border });
});

it('flags a part with an open defect in ochre, whatever else is true', () => {
  expect(fillFor({ ...base, open_defects: 1, error: 'GEOSException' }, CELL_FILL))
    .toBe(CELL_FILL.defect);
});

it('separates a render error from a timeout', () => {
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
  const states: [Cell, CellState][] = [
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

it('gives every state cellState can produce an entry in the palette', () => {
  const cells: Cell[] = [
    cell('a', 0, null, { open_defects: 1 }),
    cell('b', 1, null, { error: 'TimeoutError' }),
    cell('c', 2, null, { error: 'GEOSException' }),
    cell('d', 3, null, { open_defects_elsewhere: 1 }),
    cell('e', 4, null, { error_elsewhere: true }),
    cell('f', 5, null),
  ];
  for (const c of cells) {
    expect(CELL_STATES).toContain(cellState(c));
    expect(CELL_FILL[cellState(c)]).toBeDefined();
  }
});

it('calls a sticker out of scope, not broken, whatever else it carries', () => {
  expect(cellState(cell('a', 0, null, { out_of_scope: true }))).toBe('outOfScope');
  expect(cellState(cell('b', 1, null, { out_of_scope: true, error: 'TimeoutError' })))
    .toBe('outOfScope');
  expect(cellState(cell('c', 2, null, { out_of_scope: true, open_defects: 1 })))
    .toBe('outOfScope');
});

it('tallies each cell into its own state, and nowhere else', () => {
  const cells: Cell[] = [
    cell('a', 0, null, { open_defects: 1 }),
    cell('b', 1, null, { open_defects: 2 }),
    cell('c', 2, null, { error: 'TimeoutError' }),
    cell('d', 3, null, { error: 'GEOSException' }),
    cell('e', 4, null, { open_defects_elsewhere: 1 }),
    cell('f', 5, null, { error_elsewhere: true }),
    cell('g', 6, null),
    cell('h', 7, null, { out_of_scope: true }),
    cell('i', 8, null, { accepted_defects: 1 }),
  ];
  expect(tally(cells)).toEqual({
    unknown: 1, outOfScope: 1, timeout: 1, failed: 1, defect: 2, accepted: 1,
    problemElsewhere: 1, defectElsewhere: 1,
  });
});

it('tallies an empty corpus as all zeros', () => {
  expect(tally([])).toEqual({
    unknown: 0, outOfScope: 0, timeout: 0, failed: 0, defect: 0, accepted: 0,
    problemElsewhere: 0, defectElsewhere: 0,
  });
});

it('leaves the highlighted state exactly as painted with no highlight at all', () => {
  const timedOut = cell('a', 0, null, { error: 'TimeoutError' });
  const plain = paintCommands({
    cells: [timedOut], rects: [rects[0]!], visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
  });
  const matched = paintCommands({
    cells: [timedOut], rects: [rects[0]!], visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
    highlight: 'timeout',
  });
  expect(matched).toEqual(plain);
});

it('dims a fill cell outside the highlighted state to the unknown field, without a border', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, null, { open_defects: 1 })], rects: [rects[0]!], visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
    highlight: 'timeout',
  });
  expect(cmd).toEqual({ kind: 'fill', dx: 0, dy: 0, dw: 10, dh: 10,
                        fill: CELL_FILL.unknown.fill, border: null, borderWidth: 0,
                        shape: 'square', slash: false, glyph: undefined,
                        captions: [] });
});

it('reduces alpha on a drawn cell outside the highlighted state, and leaves a matching one alone', () => {
  const img = {} as HTMLImageElement;
  const manifest: SheetManifest = {
    level: 32, gutter: 2, pitch: 36, cols: 2, rows: 2, count: 4, size: 72,
    baked: { a: 'sha-a' },
  };
  const [dimmed] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { error: 'TimeoutError' })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    loose: new Map([['a', img]]), highlight: 'defect',
  });
  expect(dimmed).toMatchObject({ kind: 'image', alpha: expect.any(Number) });
  expect((dimmed as { alpha: number }).alpha).toBeLessThan(1);

  const [full] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { error: 'TimeoutError' })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    loose: new Map([['a', img]]), highlight: 'timeout',
  });
  expect((full as { alpha?: number }).alpha).toBeUndefined();
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

it('marks exactly one command as the caret', () => {
  const cmds = paintCommands({
    cells: [cell('a', 0, null), cell('b', 1, null), cell('c', 2, null)],
    rects: [rects[0]!, rects[1]!, { x: 40, y: 0, w: 10, h: 10 }],
    visible: [0, 1, 2],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest, caret: 1,
  });
  const cells = cmds.filter((c) => c.kind !== 'label');
  expect(cells.filter((c) => c.caret === true)).toHaveLength(1);
  expect(cells[1]).toMatchObject({ caret: true });
  expect(cells[0]!.caret).toBeUndefined();
  expect(cells[2]!.caret).toBeUndefined();
});

it('lets a cell carry both the defect frame and the caret', () => {
  const img = {} as HTMLImageElement;
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { open_defects: 1 })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    loose: new Map([['a', img]]), caret: 0,
  });
  expect(cmd).toMatchObject({ border: CELL_FILL.defect.border, caret: true });
});

it('badges a cell once it is drawn big enough to hold one, one tag per corner', () => {
  const both = cell('a', 0, 'sha-a', { tags: ['retired', 'popular'] });
  expect(badgesFor(both, 200).map((b) => [b.text ?? b.mark, b.corner]))
    .toEqual([['archive', 'br'], ['star', 'tl']]);
  expect(badgesFor(both, 20)).toEqual([]);
  expect(badgesFor(cell('b', 1, 'sha-b', { tags: ['minifig'] }), 200)).toEqual([]);
});

it('gives retired and updated the same corner, never both at once', () => {
  const stopped = badgesFor(cell('a', 0, 'sha-a', { tags: ['retired'] }), 200);
  const replaced = badgesFor(cell('b', 1, 'sha-b', { tags: ['updated'] }), 200);
  expect(stopped.map((b) => [b.tag, b.mark, b.corner])).toEqual([['retired', 'archive', 'br']]);
  expect(replaced.map((b) => [b.tag, b.mark, b.corner])).toEqual([['updated', 'redo', 'br']]);
});

it('strips the kind badges in tag order, system before property', () => {
  const part = cell('a', 0, 'sha-a',
    { tags: ['technic', 'electric', 'printed', 'retired'] });
  expect(stripFor(part, 200).map((b) => b.tag))
    .toEqual(['technic', 'electric', 'printed']);
  expect(stripFor(part, 20)).toEqual([]);
});

it('gives the property family one field and each system badge its own', () => {
  const part = cell('a', 0, 'sha-a', { tags: ['duplo', 'magnet', 'printed'] });
  const [system, ...properties] = stripFor(part, 200);
  expect(system!.field).not.toEqual(PROPERTY_FIELD);
  expect(properties.map((b) => b.field)).toEqual([PROPERTY_FIELD, PROPERTY_FIELD]);
  // Duplo is red on white, and every baked thumbnail sits on a white ground.
  expect(system!.stroke).toBeTruthy();
});

it('lets electric off the shared field, a bright bolt on black', () => {
  const [bolt] = stripFor(cell('a', 0, 'sha-a', { tags: ['electric'] }), 200);
  expect(bolt!.field).not.toEqual(PROPERTY_FIELD);
  expect(bolt!.ink).toEqual('#ffd60a');
});

it('draws a letter at twice the height of a mark in the same disc', () => {
  const { size, radius } = badgeGeometry(200);
  expect(size).toBe(20);
  expect(radius * 0.66).toBeCloseTo(size * 0.475, 2);
  // At the badge floor a mark is a little over 4px across.
  expect(badgeGeometry(56).radius * 0.66).toBeCloseTo(4.28, 2);
});

it('puts the strip on a drawn cell', () => {
  const [cmd] = paintCommands({
    cells: [cell('a', 0, 'sha-a', { tags: ['technic', 'electric'] })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 20, y: 20 } }, palette: CELL_FILL, manifest,
  });
  expect((cmd as { strip?: { tag: string }[] }).strip?.map((b) => b.tag))
    .toEqual(['technic', 'electric']);
});

it('captions a large cell with its years and its part number, and a small one with nothing', () => {
  const part = cell('3001', 0, 'sha-a', { year_from: 1979, year_to: 2026 });
  expect(captionsFor(part, 200, CAPTION_ON_FILL).map((c) => [c.text, c.corner]))
    .toEqual([['1979–', 'tr'], ['3001', 'bl']]);
  expect(captionsFor(part, 60, CAPTION_ON_FILL)).toEqual([]);
  // no years known: the part number still earns its corner
  expect(captionsFor(cell('b', 1, 'sha-b'), 200, CAPTION_ON_FILL).map((c) => c.text))
    .toEqual(['b']);
});

it('captions an undrawn cell in white, and leaves an out-of-scope one alone', () => {
  const at = (over: Partial<Cell>) => {
    const [cmd] = paintCommands({
      cells: [cell('3001', 0, null, over)], rects, visible: [0],
      cam: { x: 0, y: 0, scale: { x: 20, y: 20 } }, palette: CELL_FILL, manifest: null,
    });
    return cmd as { captions?: { text: string; ink: string }[] };
  };
  expect(at({ error: 'TimeoutError' }).captions?.map((c) => c.ink))
    .toEqual([CAPTION_ON_FILL]);
  expect(at({ out_of_scope: true, category: 'Sticker' }).captions).toBeUndefined();
});

it('carries the badge on the drawn cell, not the empty one', () => {
  const cells = [cell('a', 0, 'sha-a', { tags: ['retired'] })];
  const [cmd] = paintCommands({
    cells, rects, visible: [0], cam: { x: 0, y: 0, scale: { x: 20, y: 20 } },
    palette: CELL_FILL, manifest, loose: new Map([['a', {} as HTMLImageElement]]),
  });
  expect(cmd).toMatchObject({ kind: 'image', badges: [{ mark: 'archive', corner: 'br' }] });
});

it('strikes every undrawn cell with a border, and leaves the quiet ones alone', () => {
  const struck = (over: Partial<Cell>) => {
    const [cmd] = paintCommands({
      cells: [cell('a', 0, null, over)], rects, visible: [0],
      cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest: null,
    });
    return cmd as Extract<typeof cmd, { kind: 'fill' }>;
  };
  expect(struck({ error: 'TimeoutError' }).slash).toBe(true);
  expect(struck({ error: 'GEOSException' }).slash).toBe(true);
  expect(struck({ open_defects: 1 }).slash).toBe(true);
  expect(struck({ error_elsewhere: true }).slash).toBe(true);
  expect(struck({}).slash).toBe(false);
});

it('washes a retired cell rather than baking it a ground of its own', () => {
  const [plain] = paintCommands({
    cells: [cell('a', 0, 'sha-a')], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    vector: new Map([['a', {} as CanvasImageSource]]),
  });
  expect(plain).toMatchObject({ ground: THUMB_GROUND, wash: undefined });
  const [retired] = paintCommands({
    cells: [cell('b', 1, 'sha-b', { tags: ['retired'] })], rects, visible: [0],
    cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL, manifest,
    vector: new Map([['b', {} as CanvasImageSource]]),
  });
  expect(retired).toMatchObject({ ground: THUMB_GROUND, translucent: true });
  expect((retired as { wash?: number }).wash).toBeGreaterThan(0);
});

it('paints a fault we decided to live with in its own color, under every live one', () => {
  const accepted = cell('a', 0, null, { accepted_defects: 2 });
  expect(cellState(accepted)).toBe('accepted');
  expect(cellState(cell('b', 1, null, { accepted_defects: 1, open_defects: 1 })))
    .toBe('defect');
  expect(cellState(cell('c', 2, null, { accepted_defects: 1, error_elsewhere: true })))
    .toBe('accepted');
});

it('marks an out-of-scope cell rather than filling it, and squares the rest', () => {
  const at = (over: Partial<Cell>, scale = 1) => {
    const [cmd] = paintCommands({
      cells: [cell('a', 0, null, over)], rects, visible: [0],
      cam: { x: 0, y: 0, scale: { x: scale, y: scale } }, palette: CELL_FILL,
      manifest: null,
    });
    return cmd as { shape?: string; glyph?: string; mark?: string };
  };
  // rects are 10 world px, so scale 4 draws a 40px cell and scale 1 a 10px one
  // a sticker has a picture of its own; everything else falls back to a letter
  expect(at({ out_of_scope: true, category: 'Sticker' }, 4))
    .toMatchObject({ shape: 'circle', mark: 'sticker', glyph: undefined });
  expect(at({ out_of_scope: true, category: '~Duplo' }, 4).glyph).toBe('D');
  // and the sticker keeps its picture right down to the smallest cell
  expect(at({ out_of_scope: true, category: 'Sticker' }, 1).mark).toBe('sticker');
  expect(at({}).shape).toBe('square');
  expect(at({ error: 'TimeoutError' }).glyph).toBeUndefined();
});

const band = (over: Partial<Band> = {}): Band => ({
  key: '1970s', label: '1970s', count: 12,
  rect: { x: 0, y: 0, w: 400, h: 200 }, depth: 0, ...over,
});

describe('band labels', () => {
  const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };

  it('emits a label per band, with its count', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam, manifest: null,
      palette: CELL_FILL, bands: [band()],
    });
    const labels = out.filter((c) => c.kind === 'label');
    expect(labels).toHaveLength(1);
    expect(labels[0]).toMatchObject({ text: '1970s', count: 12, depth: 0 });
  });

  it('drops a band too narrow on screen to read', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam: { ...cam, scale: { x: 0.01, y: 0.01 } },
      manifest: null, palette: CELL_FILL, bands: [band()],
    });
    expect(out.filter((c) => c.kind === 'label')).toEqual([]);
  });

  it('emits nothing when there are no bands, as the dense grid has none', () => {
    const out = paintCommands({
      cells: [], rects: [], visible: [], cam, manifest: null, palette: CELL_FILL,
    });
    expect(out.filter((c) => c.kind === 'label')).toEqual([]);
  });
});

describe('tint', () => {
  const img = {} as HTMLImageElement;
  const drawn = { cells: [cell('a', 0, 'sha-a', { sets: 8953 })], rects, visible: [0],
                  cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, palette: CELL_FILL,
                  manifest, loose: new Map([['a', img]]) };

  it('drops the thumbnail for the ramp outside status mode', () => {
    expect(paintCommands({ ...drawn, tint: 'sets' })[0]).toMatchObject({
      kind: 'fill', fill: tintFor(drawn.cells[0]!, 'sets', CELL_FILL).fill,
    });
  });

  it('keeps the thumbnail in status mode, tint given or not', () => {
    expect(paintCommands(drawn)[0]!.kind).toBe('image');
    expect(paintCommands({ ...drawn, tint: 'status' })[0]!.kind).toBe('image');
  });

  it('keeps the vector rung and the sheet in status mode too', () => {
    const vec = {} as CanvasImageSource;
    // Byte-for-byte the pre-tint path: vector wins over loose, and a cell in
    // neither still comes off the sheet.
    expect(paintCommands({ ...drawn, vector: new Map([['a', vec]]) })[0])
      .toMatchObject({ kind: 'image', image: vec, translucent: true });
    expect(paintCommands({ ...drawn, loose: new Map() })[0]!.kind).toBe('sprite');
  });

  it('hides the sheet outside status mode, so the ramp is what is read', () => {
    expect(paintCommands({ ...drawn, loose: new Map(), tint: 'sets' })[0]!.kind)
      .toBe('fill');
  });

  it('paints an unmatched part its own tone rather than the ramp floor', () => {
    const [cmd] = paintCommands({ ...drawn, cells: [cell('a', 0, null)], tint: 'sets' });
    expect(cmd).toMatchObject({ kind: 'fill', fill: CELL_FILL.unmatched.fill });
  });
});
