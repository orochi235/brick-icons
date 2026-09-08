import { describe, expect, it } from 'vitest';
import {
  NO_CATEGORY, UNKNOWN, categoryOf, cleanCategory, coverageOf, decadeOf, groupers,
  rollUp, yearOf,
} from '@lab/corpus/facts';
import type { Cell } from '@lab/corpus/types';

const cell = (over: Partial<Cell> = {}): Cell => ({
  id: '3001', index: 0, title: 'Brick', category: 'Brick', family: null,
  printed: false, obsolete: false, base: true, out_of_scope: false, moved: false,
  year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [],
  ...over,
});

describe('cleanCategory', () => {
  it('strips the LDraw sigils a raw category name carries', () => {
    expect(cleanCategory('~Brick')).toBe('Brick');
    expect(cleanCategory('=Plate')).toBe('Plate');
    expect(cleanCategory('_Moved')).toBe('Moved');
    expect(cleanCategory('|Dish')).toBe('Dish');
    expect(cleanCategory('~=_|Tile ')).toBe('Tile');
  });

  it('leaves a plain name alone', () => {
    expect(cleanCategory('Brick')).toBe('Brick');
  });

  it('calls a bare marker and a missing name the no-category placeholder', () => {
    expect(cleanCategory('~')).toBe(NO_CATEGORY);
    expect(cleanCategory('')).toBe(NO_CATEGORY);
    expect(cleanCategory(null)).toBe(NO_CATEGORY);
  });

  it('is what categoryOf reads a cell through', () => {
    expect(categoryOf(cell({ category: '~Brick' }))).toBe('Brick');
    expect(categoryOf(cell({ category: null }))).toBe(NO_CATEGORY);
  });
});

describe('rollUp', () => {
  it('folds anything under the minimum into Other', () => {
    const cells = [...Array(30)].map(() => cell({ category: 'Brick' }))
      .concat([...Array(3)].map(() => cell({ category: 'Dish' })));
    const map = rollUp(cells, 25);
    expect(map.get('Brick')).toBe('Brick');
    expect(map.get('Dish')).toBe('Other');
  });

  it('leaves the no-category placeholder alone', () => {
    expect(rollUp([cell({ category: null })], 25).get(NO_CATEGORY)).toBe(NO_CATEGORY);
  });

  it('counts a sigil-marked name as the clean one it rolls up to', () => {
    const cells = [...Array(30)].map(() => cell({ category: '~Brick' }));
    expect(rollUp(cells, 25).get('Brick')).toBe('Brick');
  });
});

// The ranking itself is `coverage_of` in brick_icons/lab/cells.py, and
// tests/test_lab_cells.py owns its cases.
describe('coverageOf', () => {
  it('takes the label the server sent', () => {
    expect(coverageOf(cell({ coverage: 'failed', sha: 'abc' }))).toBe('failed');
  });

  it('calls a cell from an API too old to send one untried', () => {
    expect(coverageOf(cell({ sha: 'abc' }))).toBe('untried');
  });
});

describe('decadeOf and yearOf', () => {
  it('names the decade a part first appeared in', () => {
    expect(decadeOf(cell({ year_from: 1974 }))).toBe('1970s');
    expect(yearOf(cell({ year_from: 1974 }))).toBe('1974');
  });

  it('calls an undated part unknown at both levels', () => {
    expect(decadeOf(cell())).toBe(UNKNOWN);
    expect(yearOf(cell())).toBe(UNKNOWN);
  });
});

describe('groupers', () => {
  it('gives the ungrouped wall no keys at all', () => {
    expect(groupers('none', new Map())).toEqual([]);
  });

  it('groups a category through its rolled-up name', () => {
    const [key] = groupers('category', new Map([['Dish', 'Other']]));
    expect(key!(cell({ category: 'Dish' }))).toBe('Other');
    expect(key!(cell({ category: 'Brick' }))).toBe('Other');
  });

  it('is the only two-level grouping for release', () => {
    expect(groupers('release', new Map())).toHaveLength(2);
    expect(groupers('coverage', new Map())).toHaveLength(1);
  });
});
