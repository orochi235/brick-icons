import { expect, it } from 'vitest';
import { fitBounds, levelFor, pickLevel, toScreen, toWorld, zoomAt }
  from '@lab/corpus/camera';

const cam = { x: 0, y: 0, scale: 2 };

it('maps world to screen and back', () => {
  expect(toScreen(cam, 10, 20)).toEqual({ x: 20, y: 40 });
  expect(toWorld(cam, 20, 40)).toEqual({ x: 10, y: 20 });
});

it('keeps the point under the cursor fixed while zooming', () => {
  const before = toWorld(cam, 100, 100);
  const next = zoomAt(cam, 100, 100, 2);
  expect(toScreen(next, before.x, before.y)).toEqual({ x: 100, y: 100 });
});

it('clamps zoom to the allowed range', () => {
  expect(zoomAt(cam, 0, 0, 1e6).scale).toBeLessThanOrEqual(64);
  expect(zoomAt(cam, 0, 0, 1e-6).scale).toBeGreaterThanOrEqual(0.01);
});

it('fits bounds inside a viewport', () => {
  const fitted = fitBounds({ w: 100, h: 50 }, { width: 200, height: 200 });
  expect(fitted.scale).toBe(2);
});

it('does not hand back Infinity for an empty wall', () => {
  expect(fitBounds({ w: 0, h: 0 }, { width: 200, height: 200 }).scale).toBe(1);
});

it('picks the coarsest level that covers the on-screen cell size', () => {
  expect(levelFor(4)).toBe(8);
  expect(levelFor(20)).toBe(32);
  expect(levelFor(200)).toBe(128);
});

it('holds the current level across the whole hysteresis dead zone', () => {
  // The 8/32 boundary is 16px, so the dead zone is [16*0.67, 16*1.5] = [10.7, 24].
  // Inside it the level in hand wins, whichever one that is -- which is the
  // entire point: a zoom parked on 16px would otherwise re-upload every frame.
  expect(pickLevel(8, 20)).toBe(8);    // wants 32, not past 24 yet
  expect(pickLevel(32, 12)).toBe(32);  // wants 8, not below 10.7 yet
});

it('swaps once the zoom is clearly past the dead zone', () => {
  expect(pickLevel(8, 30)).toBe(32);
  expect(pickLevel(32, 5)).toBe(8);
});

it('leaves the level alone when it is already the right one', () => {
  expect(pickLevel(8, 10)).toBe(8);
  expect(pickLevel(32, 40)).toBe(32);
});
