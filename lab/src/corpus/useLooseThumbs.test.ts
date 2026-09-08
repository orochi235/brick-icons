import { expect, it } from 'vitest';
import { thumbUrl, wanted } from '@lab/corpus/useLooseThumbs';
import type { Cell } from '@lab/corpus/types';

const cell = (id: string, index: number, sha: string | null): Cell => ({
  id, index, title: id, category: null, family: null, printed: false, obsolete: false, base: true,
  out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [],
});

it('names the slot and cache-busts on the render sha', () => {
  expect(thumbUrl(cell('3001', 0, 'deadbeefcafe'), 'naive'))
    .toBe('/api/thumbs/naive/128/3001.webp?v=deadbeef');
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

it('keeps asking for cells behind the cap once the front of the view is in hand', () => {
  /* The cap used to count cells already in hand, so a viewport holding more
     than MAX_IN_FLIGHT of them starved everything behind them -- and the
     requested set only grows, so the wall stopped loading for good. */
  const many = Array.from({ length: 500 }, (_, i) => cell(`c${i}`, i, `sha${i}`));
  const all = many.map((_, i) => i);
  const have = new Set(many.slice(0, 200).map((c) => c.id));
  const next = wanted(many, all, 128, have);
  expect(next.length).toBe(200);
  expect(next[0]!.id).toBe('c200');
});
