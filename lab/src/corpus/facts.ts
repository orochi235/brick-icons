import type { Cell } from '@lab/corpus/types';

/** A part that matched nothing outside, at every grouping level. Never the low
 *  end of a ramp: "we do not know" and "1954, never used" are different. */
export const UNKNOWN = 'unknown';

/** A part whose description began with a bare marker, and so names no
 *  category of its own. */
export const NO_CATEGORY = '-';

export type Coverage = 'defect' | 'failed' | 'timeout' | 'drawn' | 'untried'
  | 'notApplicable';

const COVERAGE_ORDER: Coverage[] =
  ['defect', 'failed', 'timeout', 'drawn', 'untried', 'notApplicable'];

/** The label the server put on the cell. Derived in `cells.py` so the wall's
 *  grouping and the dashboard's tallies cannot disagree about what `drawn`
 *  means; an API older than that field falls back to `untried`, which is what
 *  a wall with no renders showed anyway. */
export function coverageOf(cell: Cell): Coverage {
  return cell.coverage ?? 'untried';
}

/** An LDraw category without its leading sigil. The catalog sends the raw
 *  name, so the marker has to come off here before anything groups on it. */
export function cleanCategory(raw: string | null): string {
  const plain = (raw ?? '').replace(/^[~=_|]+/, '').trim();
  return plain.length > 0 ? plain : NO_CATEGORY;
}

export function categoryOf(cell: Cell): string {
  return cleanCategory(cell.category);
}

export function decadeOf(cell: Cell): string {
  return cell.year_from === null ? UNKNOWN : `${Math.floor(cell.year_from / 10) * 10}s`;
}

export function yearOf(cell: Cell): string {
  return cell.year_from === null ? UNKNOWN : String(cell.year_from);
}

/** Clean category to the group it is drawn under.
 *
 *  Grouping and the facet list use different thresholds on purpose: a labeled
 *  block of three cells is confetti, but a checkbox costs one row. */
export function rollUp(cells: Cell[], minimum = 25): Map<string, string> {
  const counts = new Map<string, number>();
  for (const c of cells) {
    const name = categoryOf(c);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  const out = new Map<string, string>();
  for (const [name, n] of counts) {
    out.set(name, name === NO_CATEGORY || n >= minimum ? name : 'Other');
  }
  return out;
}

export type Grouping = 'none' | 'coverage' | 'category' | 'release';

/** The key functions each grouping needs, outermost first. `release` is the
 *  only two-level one. */
export function groupers(grouping: Grouping,
                         rolled: Map<string, string>):
                         ((c: Cell) => string)[] {
  switch (grouping) {
    case 'none': return [];
    case 'coverage': return [coverageOf];
    case 'category': return [(c) => rolled.get(categoryOf(c)) ?? 'Other'];
    case 'release': return [decadeOf, yearOf];
  }
}

export { COVERAGE_ORDER };
