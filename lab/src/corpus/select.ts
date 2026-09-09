import {
  CLASS_SPECS, DEFAULT_SHOWN, filterTable, sortTable,
  type Filter, type Shown, type Sort,
} from '@lab/corpus/criteria';
import { categoryOf, type Grouping } from '@lab/corpus/facts';
import { naturalCompare } from '@lab/corpus/natural';
import type { TintMode } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';

export interface Selection {
  sort: Sort;
  filter: Filter;
  shown: Shown;
  grouping: Grouping;
  tint: TintMode;
  /** Clean category names to leave off the wall entirely. */
  excluded: string[];
  /** Badge tags that keep a cell on the wall. Any one of them, not all:
   *  picking `technic` and then `duplo` asks to see both families, and no
   *  part is ever both, so narrowing would empty the wall. */
  badges: string[];
  /** Which way `release` runs, and nothing else. */
  desc: boolean;
}

const SORT = sortTable();
const FILTER = filterTable();

export function applySelection(cells: Cell[], selection: Selection): Cell[] {
  const shown = selection.shown ?? DEFAULT_SHOWN;
  const hidden = CLASS_SPECS.filter((c) => !shown[c.key]);
  const off = new Set(selection.excluded);
  const badges = selection.badges ?? [];
  const keep = FILTER[selection.filter].keep;
  const kept = cells.filter((c) => keep(c)
                                   && !hidden.some((h) => h.member(c))
                                   && (badges.length === 0
                                       || badges.some((t) => c.tags?.includes(t)))
                                   && !off.has(categoryOf(c)));
  const { value, desc } = SORT[selection.sort];
  return kept.slice().sort((a, b) => {
    const ka = value(a);
    const kb = value(b);
    if (ka === null || ka === undefined) return kb === null ? 0 : 1;
    if (kb === null || kb === undefined) return -1;
    if (ka === kb) return naturalCompare(a.id, b.id);
    if (typeof ka === 'string' && typeof kb === 'string') {
      return naturalCompare(ka, kb) * (desc ? -1 : 1);
    }
    return (ka < kb ? -1 : 1) * (desc ? -1 : 1);
  });
}
