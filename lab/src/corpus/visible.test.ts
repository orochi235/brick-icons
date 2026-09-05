import { expect, it } from 'vitest';
import { visibleRange } from '@lab/corpus/visible';

const rects = [
  { x: 0, y: 0, w: 10, h: 10 },
  { x: 20, y: 0, w: 10, h: 10 },
  { x: 0, y: 20, w: 10, h: 10 },
];

it('returns the indices intersecting the viewport', () => {
  expect(visibleRange(rects, { x: 0, y: 0, scale: 1 },
                      { width: 15, height: 15 })).toEqual([0]);
});

it('includes a rect only partly on screen', () => {
  expect(visibleRange(rects, { x: 5, y: 0, scale: 1 },
                      { width: 20, height: 15 })).toEqual([0, 1]);
});

it('returns nothing when the camera is off the wall', () => {
  expect(visibleRange(rects, { x: 500, y: 500, scale: 1 },
                      { width: 20, height: 20 })).toEqual([]);
});
