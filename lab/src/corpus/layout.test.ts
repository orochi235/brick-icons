import { expect, it } from 'vitest';
import { gridLayout } from '@lab/corpus/layout';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number): Cell => ({
  id, index, title: id, category: 'Brick', family: null, printed: false, obsolete: false, base: true,
  out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null, open_defects: 0, open_defects_elsewhere: 0, accepted_defects: 0,
  error_elsewhere: false,
});

const cells = [cell('a', 0), cell('b', 1), cell('c', 2), cell('d', 3)];

it('fills row-major at the given pitch', () => {
  const { rects } = gridLayout(cells, { cell: 10, gap: 2, cols: 2 });
  expect(rects[0]).toEqual({ x: 0, y: 0, w: 10, h: 10 });
  expect(rects[1]).toEqual({ x: 12, y: 0, w: 10, h: 10 });
  expect(rects[2]).toEqual({ x: 0, y: 12, w: 10, h: 10 });
});

it('reports bounds that contain every rect', () => {
  const { bounds } = gridLayout(cells, { cell: 10, gap: 2, cols: 2 });
  expect(bounds).toEqual({ w: 22, h: 22 });
});

it('is a function of the array order, not of cell.index', () => {
  const reversed = [...cells].reverse();
  const { rects } = gridLayout(reversed, { cell: 10, gap: 2, cols: 2 });
  expect(rects[0]).toEqual({ x: 0, y: 0, w: 10, h: 10 });
});

it('lays out an empty corpus without dividing by zero', () => {
  expect(gridLayout([], { cell: 10, gap: 2, cols: 2 }))
    .toEqual({ rects: [], bands: [], bounds: { w: 0, h: 0 } });
});

it('reports no bands, because a dense grid has no groups', () => {
  const out = gridLayout([cell('a', 0), cell('b', 1)], { cell: 32, gap: 4, cols: 2 });
  expect(out.bands).toEqual([]);
});
