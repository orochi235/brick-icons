import {
  CLASS_SPECS, DEFAULT_SHOWN, filterTable, sortTable,
  type Filter, type Shown, type Sort,
} from '@lab/corpus/criteria';
import { categoryOf, type Grouping } from '@lab/corpus/facts';
import { byAxis } from '@lab/corpus/paint';
import { naturalCompare } from '@lab/corpus/natural';
import type { RampName, TintMode } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';

export interface Selection {
  sort: Sort;
  filter: Filter;
  shown: Shown;
  grouping: Grouping;
  tint: TintMode;
  /** Which gradient a measured tint is drawn in. Ignored by `status`,
   *  which uses the state palette rather than a ramp. */
  gradient: RampName;
  /** Clean category names to leave off the wall entirely. */
  excluded: string[];
  /** Badge tags that keep a cell on the wall, read through `BADGE_AXES`:
   *  alternatives within one axis, narrowing across them. */
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
  const axes = byAxis(badges);
  const kept = cells.filter((c) => keep(c)
                                   && !hidden.some((h) => h.member(c))
                                   && axes.every((group) =>
                                        group.some((t) => c.tags?.includes(t)))
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
