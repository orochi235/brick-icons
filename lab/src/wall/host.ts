import { projectColumn, type Facts } from '@pezlie/wall/src/derive';
import { bandedLayout, blockLayout, type GroupKey } from '@pezlie/wall/src/grouped';
import type { Layout } from '@pezlie/wall/src/layout';
import type { CorpusSpec } from '@pezlie/wall/src/schema';
import type { WallGrouping } from '@pezlie/wall/src/WallView';
import { BRICK_ICONS } from '@pezlie/host-brick-icons/src/spec';
import {
  categoryOf, COVERAGE_ORDER, coverageOf, decadeOf, rollUpCounts, yearOf,
} from '@lab/corpus/facts';
import { MARK_SHAPES } from '@lab/corpus/markShapes';
import type { Cell } from '@lab/corpus/types';

export const SPEC: CorpusSpec<Cell> = { ...BRICK_ICONS, marks: MARK_SHAPES };

const BY_COVERAGE: GroupKey<Cell> = { reads: ['coverage'], of: coverageOf };
const BY_DECADE: GroupKey<Cell> = { reads: ['year_from'], of: decadeOf };
const BY_YEAR: GroupKey<Cell> = { reads: ['year_from'], of: yearOf };
const BY_CATEGORY: GroupKey<Cell> = { reads: ['category'], of: categoryOf };

// One key per snapshot and fold: pezlie caches a column per key object, so a
// fresh key on every layout would add a column each time the wall re-sorts.
const rolledKeys = new WeakMap<Facts<Cell>, Map<string, GroupKey<Cell>>>();

/** Rolled up over what is on the wall, as `CorpusWall` does. A grouping key
 *  sees one item at a time, so the names are counted across the rows first. */
export const byCategory: Layout<Cell> = (input, opts) => {
  if (!input.facts) throw new Error('a grouped layout needs the facts');
  const column = projectColumn(input.facts, BY_CATEGORY, BY_CATEGORY.reads,
                               BY_CATEGORY.of);
  const counts = new Map<string, number>();
  for (const row of input.rows) {
    const name = String(column.values[column.codes[row]!]);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const rolled = rollUpCounts(counts);
  const folded = JSON.stringify(
    [...rolled].filter(([name, to]) => name !== to).map(([name]) => name).sort());
  let keys = rolledKeys.get(input.facts);
  if (!keys) rolledKeys.set(input.facts, keys = new Map());
  let key = keys.get(folded);
  if (!key) {
    key = { reads: ['category'], of: (c) => rolled.get(categoryOf(c)) ?? 'Other' };
    keys.set(folded, key);
  }
  return blockLayout(key, [])(input, opts);
};

export const GROUPINGS: WallGrouping<Cell>[] = [
  { key: 'coverage', label: 'coverage',
    layout: () => blockLayout(BY_COVERAGE, COVERAGE_ORDER) },
  { key: 'category', label: 'category', layout: () => byCategory },
  { key: 'release', label: 'release year', desc: 'newest first',
    layout: (desc) => bandedLayout(BY_DECADE, BY_YEAR, desc) },
];
