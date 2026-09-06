import { expect, it } from 'vitest';
import { levelFor, pickLevel } from '@lab/corpus/levels';

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
