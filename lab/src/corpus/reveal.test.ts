import { expect, it } from 'vitest';
import { panToReveal } from '@lab/corpus/reveal';

const viewport = { width: 100, height: 100 };
const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };

it('leaves the camera alone when the rect is already fully on screen', () => {
  const rect = { x: 10, y: 10, w: 20, h: 20 };
  expect(panToReveal(rect, cam, viewport)).toEqual(cam);
});

it('pans right to reveal a rect off the right edge', () => {
  const rect = { x: 150, y: 10, w: 20, h: 20 };
  const next = panToReveal(rect, cam, viewport);
  // The rect's right edge (170) should land exactly on the viewport's.
  expect(next.x).toBe(70);
  expect(next.y).toBe(cam.y);
});

it('pans left to reveal a rect off the left edge', () => {
  const rect = { x: -50, y: 10, w: 20, h: 20 };
  const view = { x: 20, y: 0, scale: { x: 1, y: 1 } };
  const next = panToReveal(rect, view, viewport);
  expect(next.x).toBe(-50);
  expect(next.y).toBe(view.y);
});

it('pans down to reveal a rect off the bottom edge', () => {
  const rect = { x: 10, y: 150, w: 20, h: 20 };
  const next = panToReveal(rect, cam, viewport);
  expect(next.y).toBe(70);
  expect(next.x).toBe(cam.x);
});

it('pans up to reveal a rect off the top edge', () => {
  const rect = { x: 10, y: -50, w: 20, h: 20 };
  const view = { x: 0, y: 20, scale: { x: 1, y: 1 } };
  const next = panToReveal(rect, view, viewport);
  expect(next.y).toBe(-50);
  expect(next.x).toBe(view.x);
});

it('scales the pan by the camera zoom', () => {
  const rect = { x: 60, y: 10, w: 20, h: 20 };
  const view = { x: 0, y: 0, scale: { x: 2, y: 2 } };
  // On screen: rect spans [120, 160], past the 100-wide viewport.
  const next = panToReveal(rect, view, viewport);
  expect(next.x).toBe(30); // 60 - (100-40)/2
});
