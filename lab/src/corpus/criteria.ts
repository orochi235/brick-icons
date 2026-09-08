/** Everything a sort may read off an item. Deliberately narrower than `Cell`:
 *  it is what a host outside this project would have to supply, so a sort
 *  that reached past it would not survive the move. */
export interface SortFacts {
  id: string;
  category: string | null;
  status: string;
  extra_d99: number | null;
  secs: number | null;
  made_at: string | null;
  year_from: number | null;
  sets: number | null;
}

export interface SortSpec {
  key: string;
  /** What the order menu calls it. */
  label: string;
  /** null for an item the sort has no answer for. */
  value: (facts: SortFacts) => string | number | null;
  desc: boolean;
}

// Metrics read worst-first; the descriptive keys read alphabetically. Both put
// "no answer" last, so an unmeasured part never displaces a bad one.
export const SORT_SPECS = [
  { key: 'id', label: 'id',
    value: (f: SortFacts) => f.id, desc: false },
  { key: 'category', label: 'category',
    value: (f: SortFacts) => f.category, desc: false },
  { key: 'status', label: 'status',
    value: (f: SortFacts) => f.status, desc: false },
  { key: 'extra_d99', label: 'extra_d99',
    value: (f: SortFacts) => f.extra_d99, desc: true },
  { key: 'secs', label: 'secs',
    value: (f: SortFacts) => f.secs, desc: true },
  { key: 'made_at', label: 'made_at',
    value: (f: SortFacts) => f.made_at, desc: true },
  { key: 'year', label: 'year',
    value: (f: SortFacts) => f.year_from, desc: false },
  { key: 'sets', label: 'sets',
    value: (f: SortFacts) => f.sets, desc: true },
] as const satisfies readonly SortSpec[];

/** Every order the wall can be put in. Derived, so it widens with the table
 *  above and nothing else has to be told. */
export type Sort = (typeof SORT_SPECS)[number]['key'];

/** Everything a filter may read off an item. */
export interface FilterFacts {
  sha: string | null;
  error: string | null;
  printed: boolean;
  obsolete: boolean;
  base: boolean;
}

export interface FilterSpec {
  key: string;
  /** What the show menu calls it. */
  label: string;
  keep: (facts: FilterFacts) => boolean;
}

/** One class of cell to look at, out of everything the wall is made of. */
export const FILTER_SPECS = [
  { key: 'all', label: 'all', keep: () => true },
  { key: 'rendered', label: 'rendered', keep: (f: FilterFacts) => f.sha !== null },
  { key: 'unrendered', label: 'unrendered', keep: (f: FilterFacts) => f.sha === null },
  { key: 'errors', label: 'errors', keep: (f: FilterFacts) => f.error !== null },
  { key: 'printed', label: 'printed', keep: (f: FilterFacts) => f.printed },
  { key: 'obsolete', label: 'obsolete', keep: (f: FilterFacts) => f.obsolete },
  { key: 'base', label: 'base', keep: (f: FilterFacts) => f.base },
] as const satisfies readonly FilterSpec[];

export type Filter = (typeof FILTER_SPECS)[number]['key'];

/** Everything a class predicate may read off an item. */
export interface ClassFacts {
  moved: boolean;
  out_of_scope: boolean;
}

export interface ClassSpec {
  key: string;
  /** What the class checkbox calls it. */
  label: string;
  member: (facts: ClassFacts) => boolean;
  /** Whether the wall starts with this class on it. */
  shown: boolean;
}

/** Classes of cell the wall leaves out unless asked. Separate from `filter`,
 *  which picks one class to look at: these say what the map is made of at
 *  all, and a `~Moved to` redirect is not a part anyone can draw.
 *
 *  Redirects are off by default; out-of-scope parts stay on the map in their
 *  own color, because knowing what is not being drawn is the point of it. */
export const CLASS_SPECS = [
  { key: 'moved', label: 'moved',
    member: (f: ClassFacts) => f.moved, shown: false },
  { key: 'outOfScope', label: 'out of scope',
    member: (f: ClassFacts) => f.out_of_scope, shown: true },
] as const satisfies readonly ClassSpec[];

export type CellClass = (typeof CLASS_SPECS)[number]['key'];
export type Shown = Record<CellClass, boolean>;

export function sortKeys(): Sort[] {
  return SORT_SPECS.map((s) => s.key);
}

export function filterKeys(): Filter[] {
  return FILTER_SPECS.map((f) => f.key);
}

export function classKeys(): CellClass[] {
  return CLASS_SPECS.map((c) => c.key);
}

export function sortTable(): Record<Sort, SortSpec> {
  return Object.fromEntries(SORT_SPECS.map((s) => [s.key, s])) as Record<Sort, SortSpec>;
}

export function filterTable(): Record<Filter, FilterSpec> {
  return Object.fromEntries(FILTER_SPECS.map((f) => [f.key, f])) as Record<Filter, FilterSpec>;
}

export const DEFAULT_SHOWN: Shown =
  Object.fromEntries(CLASS_SPECS.map((c) => [c.key, c.shown])) as Shown;
