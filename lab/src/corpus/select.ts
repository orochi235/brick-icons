import { categoryOf, type Grouping } from '@lab/corpus/facts';
import type { TintMode } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';

export const SORTS = ['id', 'category', 'status', 'extra_d99', 'secs',
                      'made_at', 'year', 'sets'] as const;
export const FILTERS = ['all', 'rendered', 'unrendered', 'errors', 'printed',
                        'obsolete', 'base'] as const;

export type Sort = typeof SORTS[number];
export type Filter = typeof FILTERS[number];

/** Classes of cell the wall leaves out unless asked. Separate from `filter`,
 *  which picks one class to look at: these say what the map is made of at
 *  all, and a `~Moved to` redirect is not a part anyone can draw. */
export const CLASSES = ['moved', 'outOfScope'] as const;
export type CellClass = typeof CLASSES[number];
export type Shown = Record<CellClass, boolean>;

/** Redirects are off by default; out-of-scope parts stay on the map in their
 *  own color, because knowing what is not being drawn is the point of it. */
export const DEFAULT_SHOWN: Shown = { moved: false, outOfScope: true };

export const CLASS_LABEL: Record<CellClass, string> = {
  moved: 'moved',
  outOfScope: 'out of scope',
};

const IN_CLASS: Record<CellClass, (c: Cell) => boolean> = {
  moved: (c) => c.moved,
  outOfScope: (c) => c.out_of_scope,
};

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

const KEEP: Record<Filter, (c: Cell) => boolean> = {
  all: () => true,
  rendered: (c) => c.sha !== null,
  unrendered: (c) => c.sha === null,
  errors: (c) => c.error !== null,
  printed: (c) => c.printed,
  obsolete: (c) => c.obsolete,
  base: (c) => c.base,
};

// Metrics read worst-first; the descriptive keys read alphabetically. Both put
// "no answer" last, so an unmeasured part never displaces a bad one.
const DESCENDING: ReadonlySet<Sort> =
  new Set(['extra_d99', 'secs', 'made_at', 'sets']);

function key(cell: Cell, sort: Sort): string | number | null {
  switch (sort) {
    case 'id': return cell.id;
    case 'category': return cell.category;
    case 'status': return cell.status;
    case 'extra_d99': return cell.extra_d99;
    case 'secs': return cell.secs;
    case 'made_at': return cell.made_at;
    case 'year': return cell.year_from;
    case 'sets': return cell.sets;
  }
}

export function applySelection(cells: Cell[], selection: Selection): Cell[] {
  const shown = selection.shown ?? DEFAULT_SHOWN;
  const hidden = CLASSES.filter((c) => !shown[c]);
  const off = new Set(selection.excluded);
  const badges = selection.badges ?? [];
  const kept = cells.filter((c) => KEEP[selection.filter](c)
                                   && !hidden.some((h) => IN_CLASS[h](c))
                                   && (badges.length === 0
                                       || badges.some((t) => c.tags?.includes(t)))
                                   && !off.has(categoryOf(c)));
  const desc = DESCENDING.has(selection.sort);
  return kept.slice().sort((a, b) => {
    const ka = key(a, selection.sort);
    const kb = key(b, selection.sort);
    if (ka === null || ka === undefined) return kb === null ? 0 : 1;
    if (kb === null || kb === undefined) return -1;
    if (ka === kb) return a.id < b.id ? -1 : 1;
    return (ka < kb ? -1 : 1) * (desc ? -1 : 1);
  });
}
