import { expect, it } from 'vitest';
import { DEFAULT_SHOWN } from '@lab/corpus/criteria';
import { applySelection, type Selection } from '@lab/corpus/select';
import type { Cell } from '@lab/corpus/types';

const base: Omit<Selection, 'sort' | 'filter' | 'shown'> = {
  grouping: 'none', tint: 'status', gradient: 'ember', excluded: [], badges: [], desc: true,
};

const cell = (over: Partial<Cell> & { id: string; index: number }): Cell => ({
  title: over.id, category: 'Brick', family: null, printed: false, obsolete: false, base: true, out_of_scope: false, moved: false, year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null,
  secs: null, error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [], ...over,
});

const cells = [
  cell({ id: 'a', index: 0, sha: 'x', extra_d99: 1 }),
  cell({ id: 'b', index: 1, extra_d99: 9 }),
  cell({ id: 'c', index: 2, sha: 'y', extra_d99: 5, error: 'boom' }),
];

it('sorts by part id ascending by default', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('sorts a metric worst-first', () => {
  expect(applySelection(cells, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'c', 'a']);
});

it('puts cells with no measurement last', () => {
  const withNull = [...cells, cell({ id: 'd', index: 3 })];
  expect(applySelection(withNull, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .at(-1)!.id).toBe('d');
});

it('filters to what has no render', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'unrendered', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b']);
});

it('filters to errors', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'errors', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['c']);
});

it('filters to base parts', () => {
  const mixed = [
    cell({ id: 'a', index: 0, base: true }),
    cell({ id: 'b', index: 1, base: false, printed: true }),
    cell({ id: 'c', index: 2, base: false, obsolete: true }),
  ];
  expect(applySelection(mixed, { sort: 'id', filter: 'base', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a']);
});

it('never mutates the input', () => {
  const before = cells.map((c) => c.id);
  applySelection(cells, { sort: 'extra_d99', filter: 'all', shown: DEFAULT_SHOWN, ...base });
  expect(cells.map((c) => c.id)).toEqual(before);
});

it('leaves the moved redirects off the map until they are asked for', () => {
  const parts = [cell({ id: 'a', index: 0 }),
                 cell({ id: 'b', index: 1, moved: true })];
  const hidden = applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, ...base });
  expect(hidden.map((c) => c.id)).toEqual(['a']);
  const asked = applySelection(parts, { sort: 'id', filter: 'all',
                                        shown: { ...DEFAULT_SHOWN, moved: true }, ...base });
  expect(asked.map((c) => c.id)).toEqual(['a', 'b']);
});

it('keeps the out-of-scope parts on the map, and takes them off on request', () => {
  const parts = [cell({ id: 'a', index: 0 }),
                 cell({ id: 'b', index: 1, out_of_scope: true })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'b']);
  expect(applySelection(parts, { sort: 'id', filter: 'all',
                                 shown: { ...DEFAULT_SHOWN, outOfScope: false }, ...base })
    .map((c) => c.id)).toEqual(['a']);
});

it('leaves a category off the wall entirely when it is excluded', () => {
  const parts = [cell({ id: 'a', index: 0, category: 'Brick' }),
                 cell({ id: 'b', index: 1, category: 'Plate' })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, excluded: ['Plate'] })
    .map((c) => c.id)).toEqual(['a']);
});

it('excludes on the cleaned name, sigil and all', () => {
  const parts = [cell({ id: 'a', index: 0, category: '~Brick' }),
                 cell({ id: 'b', index: 1, category: 'Plate' })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, excluded: ['Brick'] })
    .map((c) => c.id)).toEqual(['b']);
});

it('keeps every category when nothing is excluded', () => {
  const parts = [cell({ id: 'a', index: 0, category: 'Brick' }),
                 cell({ id: 'b', index: 1, category: 'Plate' })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, excluded: [] })
    .map((c) => c.id)).toEqual(['a', 'b']);
});

it('drops a cell that either exclusion catches', () => {
  const parts = [cell({ id: 'a', index: 0, category: 'Brick' }),
                 cell({ id: 'b', index: 1, category: 'Plate' }),
                 cell({ id: 'c', index: 2, category: 'Brick', moved: true }),
                 cell({ id: 'd', index: 3, category: 'Plate', moved: true })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, excluded: ['Plate'] })
    .map((c) => c.id)).toEqual(['a']);
});

it('sorts by first year of release, oldest first', () => {
  const parts = [cell({ id: 'a', index: 0, year_from: 1998 }),
                 cell({ id: 'b', index: 1, year_from: 1962 }),
                 cell({ id: 'c', index: 2 })];
  expect(applySelection(parts, { sort: 'year', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

it('sorts by set count, most-used first', () => {
  const parts = [cell({ id: 'a', index: 0, sets: 12 }),
                 cell({ id: 'b', index: 1, sets: 900 }),
                 cell({ id: 'c', index: 2 })];
  expect(applySelection(parts, { sort: 'sets', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

it('keeps a cell carrying ANY of the picked tags, not all of them', () => {
  const tagged = [
    cell({ id: 'a', index: 0, tags: ['technic'] }),
    cell({ id: 'b', index: 1, tags: ['duplo'] }),
    cell({ id: 'c', index: 2, tags: ['sticker'] }),
  ];
  const pick = (badges: string[]) => applySelection(tagged,
    { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, ...base, badges })
    .map((c) => c.id);
  // No part is both technic and duplo, so narrowing would empty the wall --
  // picking a second badge asks to see that family too.
  expect(pick(['technic', 'duplo'])).toEqual(['a', 'b']);
  expect(pick(['technic'])).toEqual(['a']);
  expect(pick([])).toEqual(['a', 'b', 'c']);
});

it('sorts by category name, ascending, unnamed last', () => {
  const parts = [cell({ id: 'a', index: 0, category: 'Plate' }),
                 cell({ id: 'b', index: 1, category: 'Brick' }),
                 cell({ id: 'c', index: 2, category: null })];
  expect(applySelection(parts, { sort: 'category', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

// Sorting reads the raw catalog name, so a sigil sorts after every letter --
// unlike exclusion, which matches on the cleaned name.
it('sorts on the raw category, sigil and all', () => {
  const parts = [cell({ id: 'a', index: 0, category: '~Brick' }),
                 cell({ id: 'b', index: 1, category: 'Plate' })];
  expect(applySelection(parts, { sort: 'category', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a']);
});

it('sorts by status, ascending', () => {
  const parts = [cell({ id: 'a', index: 0, status: 'reviewed' }),
                 cell({ id: 'b', index: 1, status: 'broken' }),
                 cell({ id: 'c', index: 2, status: 'unreviewed' })];
  expect(applySelection(parts, { sort: 'status', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

it('sorts by render time, slowest first, unmeasured last', () => {
  const parts = [cell({ id: 'a', index: 0, secs: 0.5 }),
                 cell({ id: 'b', index: 1, secs: 12 }),
                 cell({ id: 'c', index: 2 })];
  expect(applySelection(parts, { sort: 'secs', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

it('sorts by render date, newest first, never-rendered last', () => {
  const parts = [cell({ id: 'a', index: 0, made_at: '2024-01-02T00:00:00Z' }),
                 cell({ id: 'b', index: 1, made_at: '2025-06-01T00:00:00Z' }),
                 cell({ id: 'c', index: 2 })];
  expect(applySelection(parts, { sort: 'made_at', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['b', 'a', 'c']);
});

it('breaks a tie on part id, ascending, whichever way the sort runs', () => {
  const asc = [cell({ id: 'c', index: 0, status: 'same' }),
               cell({ id: 'a', index: 1, status: 'same' }),
               cell({ id: 'b', index: 2, status: 'same' })];
  expect(applySelection(asc, { sort: 'status', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
  const desc = [cell({ id: 'c', index: 0, sets: 7 }),
                cell({ id: 'a', index: 1, sets: 7 }),
                cell({ id: 'b', index: 2, sets: 7 })];
  expect(applySelection(desc, { sort: 'sets', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('leaves cells with no key in the order they arrived', () => {
  const parts = [cell({ id: 'c', index: 0 }),
                 cell({ id: 'a', index: 1 }),
                 cell({ id: 'b', index: 2 })];
  expect(applySelection(parts, { sort: 'sets', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['c', 'a', 'b']);
});

it('filters to what has a render', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'rendered', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'c']);
});

it('keeps everything under the all filter', () => {
  expect(applySelection(cells, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a', 'b', 'c']);
});

it('filters to printed parts', () => {
  const parts = [cell({ id: 'a', index: 0, printed: true }),
                 cell({ id: 'b', index: 1 })];
  expect(applySelection(parts, { sort: 'id', filter: 'printed', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a']);
});

it('filters to obsolete parts', () => {
  const parts = [cell({ id: 'a', index: 0, obsolete: true }),
                 cell({ id: 'b', index: 1 })];
  expect(applySelection(parts, { sort: 'id', filter: 'obsolete', shown: DEFAULT_SHOWN, ...base })
    .map((c) => c.id)).toEqual(['a']);
});

it('narrows by filter, class and badge together', () => {
  const parts = [
    cell({ id: 'a', index: 0, sha: 'x', tags: ['technic'] }),
    cell({ id: 'b', index: 1, tags: ['technic'] }),
    cell({ id: 'c', index: 2, sha: 'x', tags: ['duplo'] }),
    cell({ id: 'd', index: 3, sha: 'x', tags: ['technic'], moved: true }),
  ];
  expect(applySelection(parts, { sort: 'id', filter: 'rendered', shown: DEFAULT_SHOWN,
                                 ...base, badges: ['technic'] })
    .map((c) => c.id)).toEqual(['a']);
});

it('drops a cell an excluded category catches even when a badge picked it', () => {
  const parts = [cell({ id: 'a', index: 0, category: 'Brick', tags: ['technic'] }),
                 cell({ id: 'b', index: 1, category: 'Plate', tags: ['technic'] })];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, excluded: ['Plate'], badges: ['technic'] })
    .map((c) => c.id)).toEqual(['a']);
});

it('drops a cell whose tags the server never sent when a badge is picked', () => {
  const parts = [cell({ id: 'a', index: 0, tags: ['technic'] }),
                 { ...cell({ id: 'b', index: 1 }), tags: undefined } as unknown as Cell];
  expect(applySelection(parts, { sort: 'id', filter: 'all', shown: DEFAULT_SHOWN,
                                 ...base, badges: ['technic'] })
    .map((c) => c.id)).toEqual(['a']);
});

// The server is long-lived and can be older than the page: a selection that
// reaches `applySelection` without these fields falls back rather than throwing.
it('falls back to the default classes and no badges when neither is supplied', () => {
  const parts = [cell({ id: 'a', index: 0 }),
                 cell({ id: 'b', index: 1, moved: true }),
                 cell({ id: 'c', index: 2, out_of_scope: true })];
  const bare = { sort: 'id', filter: 'all', grouping: 'none', tint: 'status',
                 excluded: [], desc: true } as unknown as Selection;
  expect(applySelection(parts, bare).map((c) => c.id)).toEqual(['a', 'c']);
});
