import type { Cell } from '@lab/corpus/types';

export const SORTS = ['id', 'category', 'status', 'extra_d99', 'secs',
                      'made_at'] as const;
export const FILTERS = ['all', 'rendered', 'unrendered', 'errors', 'printed',
                        'obsolete', 'base'] as const;

export type Sort = typeof SORTS[number];
export type Filter = typeof FILTERS[number];
export interface Selection { sort: Sort; filter: Filter }

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
const DESCENDING: ReadonlySet<Sort> = new Set(['extra_d99', 'secs', 'made_at']);

function key(cell: Cell, sort: Sort): string | number | null {
  switch (sort) {
    case 'id': return cell.id;
    case 'category': return cell.category;
    case 'status': return cell.status;
    case 'extra_d99': return cell.extra_d99;
    case 'secs': return cell.secs;
    case 'made_at': return cell.made_at;
  }
}

export function applySelection(cells: Cell[], selection: Selection): Cell[] {
  const kept = cells.filter(KEEP[selection.filter]);
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
