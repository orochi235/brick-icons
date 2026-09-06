import { expect, it } from 'vitest';
import { needsRerender, vectorUrl, wantedVector } from '@lab/corpus/useVectorThumbs';
import { VECTOR_LEVEL } from '@lab/corpus/levels';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, sha: string | null): Cell => ({
  id, index: 0, title: id, category: null, printed: false, obsolete: false, base: true,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0,
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

it('caps how many stay resident at once', () => {
  const many = Array.from({ length: 200 }, (_, i) => cell(`p${i}`, 'x'));
  expect(wantedVector(many, many.map((_, i) => i), VECTOR_LEVEL).length).toBe(96);
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
