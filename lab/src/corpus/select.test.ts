import { expect, it } from 'vitest';
import { applySelection } from '@lab/corpus/select';
import type { Cell } from '@lab/corpus/types';

const cell = (over: Partial<Cell> & { id: string; index: number }): Cell => ({
  title: over.id, category: 'Brick', printed: false, obsolete: false,
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null, open_defects: 0, open_defects_elsewhere: 0,
  error_elsewhere: false, ...over,
});

const cells = [
  cell({ id: 'a', index: 0, sha: 'x', extra_d99: 1 }),
  cell({ id: 'b', index: 1, extra_d99: 9 }),
  cell({ id: 'c', index: 2, sha: 'y', extra_d99: 5, error: 'boom' }),
];

it('sorts by part id ascending by default', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'all' })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('sorts a metric worst-first', () => {
  expect(applySelection(cells, { sort: 'extra_d99', filter: 'all' })
    .map((c) => c.id)).toEqual(['b', 'c', 'a']);
});

it('puts cells with no measurement last', () => {
  const withNull = [...cells, cell({ id: 'd', index: 3 })];
  expect(applySelection(withNull, { sort: 'extra_d99', filter: 'all' })
    .at(-1)!.id).toBe('d');
});

it('filters to what has no render', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'unrendered' })
    .map((c) => c.id)).toEqual(['b']);
});

it('filters to errors', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'errors' })
    .map((c) => c.id)).toEqual(['c']);
});

it('never mutates the input', () => {
  const before = cells.map((c) => c.id);
  applySelection(cells, { sort: 'extra_d99', filter: 'all' });
  expect(cells.map((c) => c.id)).toEqual(before);
});
