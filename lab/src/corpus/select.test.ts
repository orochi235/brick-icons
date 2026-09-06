import { expect, it } from 'vitest';
import { applySelection, DEFAULT_SHOWN } from '@lab/corpus/select';
import type { Cell } from '@lab/corpus/types';

const cell = (over: Partial<Cell> & { id: string; index: number }): Cell => ({
  title: over.id, category: 'Brick', printed: false, obsolete: false, base: true, out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null, open_defects: 0, open_defects_elsewhere: 0, accepted_defects: 0,
  error_elsewhere: false, ...over,
});

const cells = [
  cell({ id: 'a', index: 0, sha: 'x', extra_d99: 1 }),
  cell({ id: 'b', index: 1, extra_d99: 9 }),
  cell({ id: 'c', index: 2, sha: 'y', extra_d99: 5, error: 'boom' }),
];

it('sorts by part id ascending by default', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('sorts a metric worst-first', () => {
  expect(applySelection(cells, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['b', 'c', 'a']);
});

it('puts cells with no measurement last', () => {
  const withNull = [...cells, cell({ id: 'd', index: 3 })];
  expect(applySelection(withNull, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN })
    .at(-1)!.id).toBe('d');
});

it('filters to what has no render', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'unrendered', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['b']);
});

it('filters to errors', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'errors', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['c']);
});

it('filters to base parts', () => {
  const mixed = [
    cell({ id: 'a', index: 0, base: true }),
    cell({ id: 'b', index: 1, base: false, printed: true }),
    cell({ id: 'c', index: 2, base: false, obsolete: true }),
  ];
  expect(applySelection(mixed, { sort: 'id', filter: 'base', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['a']);
});

it('never mutates the input', () => {
  const before = cells.map((c) => c.id);
  applySelection(cells, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN });
  expect(cells.map((c) => c.id)).toEqual(before);
});

it('leaves the moved redirects off the map until they are asked for', () => {
  const parts = [cell({ id: 'a', index: 0 }),
                 cell({ id: 'b', index: 1, moved: true })];
  const hidden = applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN });
  expect(hidden.map((c) => c.id)).toEqual(['a']);
  const asked = applySelection(parts, { sort: 'id', filter: 'all',
                                        shown: { ...DEFAULT_SHOWN, moved: true } });
  expect(asked.map((c) => c.id)).toEqual(['a', 'b']);
});

it('keeps the out-of-scope parts on the map, and takes them off on request', () => {
  const parts = [cell({ id: 'a', index: 0 }),
                 cell({ id: 'b', index: 1, out_of_scope: true })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN })
    .map((c) => c.id)).toEqual(['a', 'b']);
  expect(applySelection(parts, { sort: 'id', filter: 'all',
                                 shown: { ...DEFAULT_SHOWN, outOfScope: false } })
    .map((c) => c.id)).toEqual(['a']);
});
