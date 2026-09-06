import { describe, expect, it } from 'vitest';
import { centerReveal, panToReveal } from '@lab/corpus/reveal';

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

it('centers an on-screen rect exactly in the middle of the viewport', () => {
  const rect = { x: 40, y: 40, w: 20, h: 20 };
  const next = centerReveal(rect, cam, viewport);
  expect(next.x).toBe(0);
  expect(next.y).toBe(0);
});

it('centers an off-screen rect too, unlike panToReveal', () => {
  const rect = { x: 500, y: 500, w: 20, h: 20 };
  const next = centerReveal(rect, cam, viewport);
  expect(next.x).toBe(460); // center 510 - half the 100-wide viewport
  expect(next.y).toBe(460);
});

it('centers scaled by the camera zoom', () => {
  const rect = { x: 60, y: 60, w: 20, h: 20 };
  const view = { x: 0, y: 0, scale: { x: 2, y: 2 } };
  const next = centerReveal(rect, view, viewport);
  expect(next.x).toBe(45); // center 70 - (100/2)/2
  expect(next.y).toBe(45);
});

describe('centerReveal zoom floor', () => {
  const cell = { x: 1000, y: 500, w: 32, h: 32 };
  const viewport = { width: 800, height: 600 };

  it('zooms in until the cell fills half the viewport height', () => {
    const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };
    const next = centerReveal(cell, cam, viewport, 0.5);
    expect(next.scale.y).toBeCloseTo((600 * 0.5) / 32);
    // and it is still centered, at the scale it arrived at
    expect(next.x).toBeCloseTo(1016 - 400 / next.scale.x);
    expect(next.y).toBeCloseTo(516 - 300 / next.scale.y);
  });

  it('scales both axes by the same factor, so cells stay square', () => {
    const cam = { x: 0, y: 0, scale: { x: 2, y: 2 } };
    const next = centerReveal(cell, cam, viewport, 0.5);
    expect(next.scale.x).toBeCloseTo(next.scale.y);
  });

  it('leaves a camera that is already closer alone', () => {
    const cam = { x: 0, y: 0, scale: { x: 40, y: 40 } };
    const next = centerReveal(cell, cam, viewport, 0.5);
    expect(next.scale).toEqual(cam.scale);
  });

  it('is the old centering with no floor asked for', () => {
    const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };
    expect(centerReveal(cell, cam, viewport)).toEqual(centerReveal(cell, cam, viewport, 0));
  });
});
