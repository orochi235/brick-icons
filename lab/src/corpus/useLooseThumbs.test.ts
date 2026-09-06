import { expect, it } from 'vitest';
import { thumbUrl, wanted } from '@lab/corpus/useLooseThumbs';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null): Cell => ({
  id, index, title: id, category: null, printed: false, obsolete: false, base: true,
  out_of_scope: false,
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, open_defects_elsewhere: 0,
  error_elsewhere: false,
});

it('names the slot and cache-busts on the render sha', () => {
  expect(thumbUrl(cell('3001', 0, 'deadbeefcafe'), 'naive'))
    .toBe('/api/thumbs/naive/128/3001.png?v=deadbeef');
});

it('wants nothing below the loose level', () => {
  expect(wanted([cell('a', 0, 'x')], [0], 32)).toEqual([]);
});

it('wants only visible cells that have a render', () => {
  const cells = [cell('a', 0, 'x'), cell('b', 1, null)];
  expect(wanted(cells, [0, 1], 128).map((c) => c.id)).toEqual(['a']);
});

it('caps how many it asks for at once', () => {
  const many = Array.from({ length: 300 }, (_, i) => cell(`p${i}`, i, 'x'));
  expect(wanted(many, many.map((_, i) => i), 128).length).toBe(200);
});
