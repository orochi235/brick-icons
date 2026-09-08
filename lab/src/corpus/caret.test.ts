import { expect, it } from 'vitest';
import { adjacent, impliedCaret } from '@lab/corpus/caret';
import { blockLayout } from '@lab/corpus/grouped';
import type { Rect } from '@lab/corpus/layout';
import type { Cell } from '@lab/corpus/types';

// A 3x3 grid, pitch 12 (cell 10, gap 2) -- rows major, matching gridLayout.
const rect = (col: number, row: number): Rect =>
  ({ x: col * 12, y: row * 12, w: 10, h: 10 });

const grid3x3: Rect[] = [];
for (let row = 0; row < 3; row++) {
  for (let col = 0; col < 3; col++) grid3x3.push(rect(col, row));
}
// indices: 0 1 2
//          3 4 5
//          6 7 8

const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };

const celled = (id: string, index: number, category: string): Cell => ({
  id, index, title: '', category, family: null, printed: false, obsolete: false,
  base: false, out_of_scope: false, moved: false, year_from: null,
  year_to: null, sets: null, colors: null, tags: [], status: 'unreviewed', sha: null,
  made_at: null, extra_d99: null, secs: null, error: null, open_defects: 0,
  review_defects: 0, accepted_defects: 0, elsewhere: [],
});

it('impliedCaret prefers a whole cell over a clipped one', () => {
  const rects: Rect[] = [
    { x: 0, y: 0, w: 10, h: 10 },   // clipped: only half on screen
    { x: 15, y: 0, w: 10, h: 10 },  // whole cell, fully on screen
  ];
  // Viewport cuts off at x=5, so rect 0 only shows half its area.
  const view = { x: 5, y: 0, scale: { x: 1, y: 1 } };
  expect(impliedCaret(rects, [0, 1], view, { width: 20, height: 10 })).toBe(1);
});

it('impliedCaret prefers the cell nearest the viewport center among equal areas', () => {
  const rects: Rect[] = [
    { x: 0, y: 0, w: 10, h: 10 },
    { x: 40, y: 0, w: 10, h: 10 },
  ];
  // Both cells fully on screen (equal area). A 12-wide viewport centers at
  // x=6, close to rect 0's center (5) and far from rect 1's (45).
  const view = { x: 0, y: 0, scale: { x: 1, y: 1 } };
  expect(impliedCaret(rects, [0, 1], view, { width: 12, height: 10 })).toBe(0);
});

it('impliedCaret is null when nothing is visible', () => {
  expect(impliedCaret(grid3x3, [], cam, { width: 100, height: 100 })).toBeNull();
});

it('adjacent finds the neighbor to the right', () => {
  expect(adjacent(grid3x3, 4, 'right')).toBe(5);
});

it('adjacent finds the neighbor to the left', () => {
  expect(adjacent(grid3x3, 4, 'left')).toBe(3);
});

it('adjacent finds the neighbor above', () => {
  expect(adjacent(grid3x3, 4, 'up')).toBe(1);
});

it('adjacent finds the neighbor below', () => {
  expect(adjacent(grid3x3, 4, 'down')).toBe(7);
});

it('picks the same-row neighbor over a nearer diagonal one', () => {
  const rects: Rect[] = [
    { x: 0, y: 0, w: 10, h: 10 },   // 0: current, center (5, 5)
    { x: 30, y: 0, w: 10, h: 10 },  // 1: same row, center (35, 5) -- dist 30
    { x: 15, y: 8, w: 10, h: 10 },  // 2: diagonal, center (20, 13) -- dist ~17, nearer
  ];
  expect(adjacent(rects, 0, 'right')).toBe(1);
});

it('wraps from the end of a row to the start of the next', () => {
  // Index 2 is the top-right corner -- nothing geometrically to its right.
  expect(adjacent(grid3x3, 2, 'right')).toBe(3);
});

it('wraps from the start of a row back to the end of the previous', () => {
  // Index 3 is the start of row two -- nothing geometrically to its left.
  expect(adjacent(grid3x3, 3, 'left')).toBe(2);
});

it('returns null going up from the top row', () => {
  expect(adjacent(grid3x3, 1, 'up')).toBeNull();
});

it('returns null going down from the bottom row', () => {
  expect(adjacent(grid3x3, 7, 'down')).toBeNull();
});

it('returns null going right from the very last cell', () => {
  expect(adjacent(grid3x3, 8, 'right')).toBeNull();
});

it('returns null going left from the very first cell', () => {
  expect(adjacent(grid3x3, 0, 'left')).toBeNull();
});

it('crosses the gutter between two blocks', () => {
  // Grouping puts whitespace between blocks, and a caret that moved by index
  // arithmetic would stop at the edge of one. These are the real rects
  // `blockLayout` lays out for two four-cell groups, three columns each.
  const cells = [
    ...['a0', 'a1', 'a2', 'a3'].map((id, i) => celled(id, i, 'A')),
    ...['b0', 'b1', 'b2', 'b3'].map((id, i) => celled(id, i + 4, 'B')),
  ];
  const { rects } = blockLayout((c) => c.category ?? '', [])(
    cells, { cell: 10, gap: 2, cols: 12 });

  // Block A's top-right cell: nothing of its own block lies to its right.
  const from = 2;
  const next = adjacent(rects, from, 'right');

  expect(next).not.toBeNull();
  expect(rects[next!]!.x).toBeGreaterThan(rects[from]!.x + rects[from]!.w);
  expect(cells[next!]!.category).toBe('B');
  // Index arithmetic would have answered 3, which sits below-left in block A.
  expect(next).not.toBe(from + 1);
});
