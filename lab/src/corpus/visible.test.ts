import { expect, it } from 'vitest';
import { visibleRange } from '@lab/corpus/visible';

const rects = [
  { x: 0, y: 0, w: 10, h: 10 },
  { x: 20, y: 0, w: 10, h: 10 },
  { x: 0, y: 20, w: 10, h: 10 },
];

it('returns the indices intersecting the viewport', () => {
  expect(visibleRange(rects, { x: 0, y: 0, scale: { x: 1, y: 1 } },
                      { width: 15, height: 15 })).toEqual([0]);
});

it('includes a rect only partly on screen', () => {
  expect(visibleRange(rects, { x: 5, y: 0, scale: { x: 1, y: 1 } },
                      { width: 20, height: 15 })).toEqual([0, 1]);
});

it('returns nothing when the camera is off the wall', () => {
  expect(visibleRange(rects, { x: 500, y: 500, scale: { x: 1, y: 1 } },
                      { width: 20, height: 20 })).toEqual([]);
});

it('covers only the slice a pinch leaves on screen', () => {
  // The whole canvas holds all three; the slice at x=18 holds only the second.
  // Without the origin a pinched wall fetches a sharper tile for every cell,
  // including the ones the pinch has pushed off the glass.
  const view = { x: 0, y: 0, scale: { x: 1, y: 1 } };
  expect(visibleRange(rects, view, { width: 40, height: 40 })).toEqual([0, 1, 2]);
  expect(visibleRange(rects, view, { x: 18, y: 0, width: 14, height: 14 }))
    .toEqual([1]);
});

it('reads an origin in the same pixels as the size, through a zoom', () => {
  // Both are screen pixels off the canvas corner, so a scale applies to the
  // origin exactly as it does to the width -- getting that wrong puts the
  // slice in the wrong place only when zoomed, which is when it is used.
  const view = { x: 0, y: 0, scale: { x: 2, y: 2 } };
  expect(visibleRange(rects, view, { x: 40, y: 0, width: 24, height: 24 }))
    .toEqual([1]);
});
