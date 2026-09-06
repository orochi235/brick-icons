import { expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { fetchText } from '@lab/corpus/svgRaster';
import {
  MAX_TARGET_PX, PIXEL_BUDGET, needsRerender, residentCap, splitWork, targetPxFor,
  useVectorThumbs, vectorUrl, wantedVector,
} from '@lab/corpus/useVectorThumbs';
import { VECTOR_LEVEL } from '@lab/corpus/levels';
import type { Cell } from '@lab/corpus/types';

vi.mock('@lab/corpus/svgRaster', () => ({
  fetchText: vi.fn(() => Promise.resolve('<svg/>')),
  rasterizeSvg: vi.fn(() => Promise.resolve({} as CanvasImageSource)),
}));

const cell = (id: string, sha: string | null): Cell => ({
  id, index: 0, title: id, category: null, printed: false, obsolete: false, base: true,
  out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, tags: [], status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0, accepted_defects: 0,
  error_elsewhere: false,
});

it('names the slot and cache-busts on the render sha', () => {
  expect(vectorUrl(cell('3001', 'deadbeefcafe'), 'naive'))
    .toBe('/api/corpus/render/naive/3001.svg?v=deadbeef');
});

it('wants nothing below the vector level', () => {
  expect(wantedVector([cell('a', 'x')], [0], 128)).toEqual([]);
});

it('wants only visible cells that have a render', () => {
  const cells = [cell('a', 'x'), cell('b', null)];
  expect(wantedVector(cells, [0, 1], VECTOR_LEVEL).map((c) => c.id)).toEqual(['a']);
});

it('keeps a screenful of small cells, where the budget holds them', () => {
  const many = Array.from({ length: 400 }, (_, i) => cell(`p${i}`, 'x'));
  const all = many.map((_, i) => i);
  expect(wantedVector(many, all, VECTOR_LEVEL, 256).length).toBe(400);
});

it('drops back to a few cells once each raster is a big one', () => {
  const many = Array.from({ length: 400 }, (_, i) => cell(`p${i}`, 'x'));
  const all = many.map((_, i) => i);
  expect(wantedVector(many, all, VECTOR_LEVEL, 1024).length)
    .toBe(Math.floor(PIXEL_BUDGET / (1024 * 1024)));
});

it('sizes a raster in device pixels, capped', () => {
  expect(targetPxFor(300, 2)).toBe(600);
  expect(targetPxFor(300, 1)).toBe(300);
  expect(targetPxFor(4000, 2)).toBe(MAX_TARGET_PX);
});

it('spends the same budget on many small rasters or few big ones', () => {
  expect(residentCap(256)).toBeGreaterThan(residentCap(1024));
  expect(residentCap(256) * 256 * 256).toBeLessThanOrEqual(PIXEL_BUDGET);
});

it('treats a never-rastered cell as needing one', () => {
  expect(needsRerender(null, 400)).toBe(true);
});

it('holds a raster whose size is still close enough to the target', () => {
  expect(needsRerender(400, 450)).toBe(false);
  expect(needsRerender(400, 500)).toBe(false);
});

it('reraster once the drawn size drifts past the threshold', () => {
  expect(needsRerender(400, 501)).toBe(true);
  expect(needsRerender(400, 299)).toBe(true);
});

it('rasterizes a cell with nothing to draw immediately', () => {
  const want = [cell('a', 'x'), cell('b', 'x')];
  const { now, onSettle } = splitWork(want, new Map([['a', { px: 400 }]]), 400);
  expect(now.map((c) => c.id)).toEqual(['b']);
  expect(onSettle).toEqual([]);
});

it('makes a merely-wrong-sized raster wait for the camera to stop', () => {
  const want = [cell('a', 'x')];
  const { now, onSettle } = splitWork(want, new Map([['a', { px: 200 }]]), 800);
  expect(now).toEqual([]);
  expect(onSettle.map((c) => c.id)).toEqual(['a']);
});

// The hook itself, where the slot change lives. A parked camera is the whole
// point: the drawn size is identical either side of the switch, so every cell
// looks like it already has a raster the right size.
it('rasterizes the new slot after a slot change, with the camera parked', async () => {
  const cells = [cell('a', 'x'), cell('b', 'y')];
  // Stable, as the wall's own memoized `visible` is -- a fresh array each
  // render re-runs the effect for free and hides the bug.
  const visible = [0, 1];
  const { result, rerender } = renderHook(
    ({ source }) => useVectorThumbs(cells, visible, VECTOR_LEVEL, source, 256),
    { initialProps: { source: 'census-naive' } });

  await waitFor(() => expect(result.current.size).toBe(2));
  vi.mocked(fetchText).mockClear();

  rerender({ source: 'census-occt' });
  await waitFor(() => expect(vi.mocked(fetchText).mock.calls.map((c) => c[0]))
    .toEqual(expect.arrayContaining([
      expect.stringContaining('/census-occt/a.svg'),
      expect.stringContaining('/census-occt/b.svg'),
    ])));
  await waitFor(() => expect(result.current.size).toBe(2));
});
