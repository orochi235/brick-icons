import { bandedLayout, blockLayout } from '@castleblack/wall/src/grouped';
import type { Layout } from '@castleblack/wall/src/layout';
import type { CorpusSpec } from '@castleblack/wall/src/schema';
import type { WallGrouping } from '@castleblack/wall/src/WallView';
import { BRICK_ICONS } from '@castleblack/host-brick-icons/src/spec';
import {
  categoryOf, COVERAGE_ORDER, coverageOf, decadeOf, rollUp, yearOf,
} from '@lab/corpus/facts';
import { MARK_SHAPES } from '@lab/corpus/markShapes';
import type { Cell } from '@lab/corpus/types';

export const SPEC: CorpusSpec<Cell> = { ...BRICK_ICONS, marks: MARK_SHAPES };

/** Rolled up over what is on the wall, as `CorpusWall` does. */
const byCategory: Layout<Cell> = (cells, opts) => {
  const rolled = rollUp([...cells]);
  return blockLayout((c: Cell) => rolled.get(categoryOf(c)) ?? 'Other', [])(cells, opts);
};

export const GROUPINGS: WallGrouping<Cell>[] = [
  { key: 'coverage', label: 'coverage', layout: () => blockLayout(coverageOf, COVERAGE_ORDER) },
  { key: 'category', label: 'category', layout: () => byCategory },
  { key: 'release', label: 'release year', desc: 'newest first',
    layout: (desc) => bandedLayout(decadeOf, yearOf, desc) },
];
