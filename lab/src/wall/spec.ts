import type {
  BadgeDef, CorpusSpec, StateDef, TintDef, VariantDef,
} from '@pezlie/wall/src/schema';
import { CLASS_SPECS, FILTER_SPECS, SORT_SPECS } from '@lab/corpus/criteria';
import { categoryOf } from '@lab/corpus/facts';
import {
  BADGE_AXES, CORNER_BADGES, STRIP_BADGES, glyphFor, isRetired, markFor,
  type CellBadge,
} from '@lab/corpus/paint';
import { STATES } from '@lab/corpus/states';
import {
  MEASURED_MODES, SCALE_IS_LOG, SCALE_LABEL, TINT_LABEL, cellValue, formatScale, scaleAt,
  type MeasuredMode,
} from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';
import { yearRange } from '@lab/corpus/years';

/** Every predicate brick-icons writes in TypeScript, as CEL. A key its tables
 *  gain without a line here is a thrown error, not a silently unmatched row. */
const STATE_MATCH: Record<string, string> = {
  unknown: 'true',
  outOfScope: 'item.out_of_scope',
  notApplicable: 'has(item.not_applicable) && item.not_applicable == true',
  review: 'item.review_defects > 0',
  defect: 'item.open_defects > 0',
  timeout: "item.error == 'TimeoutError'",
  failed: 'item.error != null',
  accepted: 'item.accepted_defects > 0',
};

const FILTER_KEEP: Record<string, string> = {
  all: 'true',
  rendered: 'item.sha != null',
  unrendered: 'item.sha == null',
  errors: 'item.error != null',
  printed: 'item.printed',
  obsolete: 'item.obsolete',
  base: 'item.base',
};

const CLASS_MEMBER: Record<string, string> = {
  moved: 'item.moved',
  outOfScope: 'item.out_of_scope',
  obsolete: 'item.obsolete',
  posed: 'has(item.posed) && item.posed == true',
};

const SORT_VALUE: Record<string, string> = {
  id: 'item.id',
  category: 'item.category',
  status: 'item.status',
  extra_d99: 'item.extra_d99',
  missing_comps: 'has(item.missing_comps) ? item.missing_comps : null',
  missing_edges: 'has(item.missing_edges) ? item.missing_edges : null',
  secs: 'item.secs',
  made_at: 'item.made_at',
  error_at: 'has(item.error_at) ? item.error_at : null',
  year: 'item.year_from',
  sets: 'item.sets',
};

function cel(table: Record<string, string>, name: string, key: string): string {
  const expr = table[key];
  if (expr === undefined) throw new Error(`brick-icons ${name} gained ${key}, which has no CEL here`);
  return expr;
}

const ELSEWHERE: VariantDef = {
  key: 'elsewhere', suffix: 'Elsewhere', label: '{label} elsewhere', list: 'elsewhere',
  precedenceDrop: 40, weight: 'thin', wash: { s: 0.30, l: 0.675 },
};

const QUIET = new Set(['outOfScope']);

const conditions = STATES.filter((s) => !s.key.endsWith(ELSEWHERE.suffix));
const withSibling = new Set(STATES.filter((s) => s.key.endsWith(ELSEWHERE.suffix))
  .map((s) => s.key.slice(0, -ELSEWHERE.suffix.length)));

const states: StateDef[] = conditions.map((s) => ({
  key: s.key, label: s.label, fill: s.fill, border: s.border, weight: s.weight,
  shape: s.shape, precedence: s.precedence,
  match: cel(STATE_MATCH, 'states', s.key),
  ...(withSibling.has(s.key) ? { variants: [ELSEWHERE.key] } : {}),
  ...(QUIET.has(s.key) ? { quiet: true } : {}),
}));

const art = ({ tag: _tag, ...rest }: CellBadge) => rest;

const badges: BadgeDef[] = [
  ...Object.values(CORNER_BADGES).map((b): BadgeDef => ({
    tag: b.tag, slot: 'corner', art: art(b),
    // The years already say the part stopped.
    ...(b.tag === 'retired' ? { yieldsTo: 'years' } : {}),
  })),
  ...Object.values(STRIP_BADGES).map((b): BadgeDef => ({ tag: b.tag, slot: 'strip', art: art(b) })),
];

// brick-icons keeps these private to tint.ts; they are its calibration, and
// the differential test fails if they drift from it.
const FIRST_YEAR = 1954;
const YEAR_SPAN = 73;
const MAX_LOG: Record<Exclude<MeasuredMode, 'year'>, number> = {
  secs: Math.log10(680),
  sets: Math.log10(8953),
  colors: Math.log10(80),
};

function position(cell: Cell, mode: MeasuredMode): number | null {
  const v = cellValue(cell, mode);
  if (v === null || v === undefined) return null;
  if (mode === 'year') return (v - FIRST_YEAR) / YEAR_SPAN;
  return Math.log10(Math.max(1, v)) / MAX_LOG[mode];
}

/** The field `cellValue` reads for each mode. */
const VALUE_FIELD: Record<MeasuredMode, string> = {
  secs: 'secs', year: 'year_from', sets: 'sets', colors: 'colors',
};

const tints: TintDef<Cell>[] = MEASURED_MODES.map((mode) => ({
  key: mode,
  label: TINT_LABEL[mode],
  scaleLabel: SCALE_LABEL[mode],
  log: SCALE_IS_LOG[mode],
  reads: [VALUE_FIELD[mode]],
  t: (cell) => position(cell, mode),
  raw: (cell) => cellValue(cell, mode),
  at: (t) => scaleAt(mode, t),
  format: (v) => formatScale(mode, v),
}));

export const BRICK_ICONS: CorpusSpec<Cell> = {
  states,
  variants: [ELSEWHERE],
  filters: FILTER_SPECS.map((f) => ({ key: f.key, label: f.label, keep: cel(FILTER_KEEP, 'filters', f.key) })),
  classes: CLASS_SPECS.map((c) => ({
    key: c.key, label: c.label, member: cel(CLASS_MEMBER, 'classes', c.key), shown: c.shown,
  })),
  sorts: SORT_SPECS.map((s) => ({
    key: s.key, label: s.label, value: cel(SORT_VALUE, 'sorts', s.key), desc: s.desc,
  })),
  tags: 'has(item.tags) ? item.tags : []',
  tagAxes: BADGE_AXES,
  facets: [{ key: 'category', label: 'category', of: { hook: 'category', reads: ['category'] } }],
  washes: "has(item.tags) && ('retired' in item.tags || 'replaced' in item.tags)",
  badges,
  captions: [
    { key: 'years', corner: 'tr', weight: 'text', text: { hook: 'years' } },
    { key: 'family', corner: 'tl', weight: 'text', text: { expr: 'item.family' } },
    { key: 'id', corner: 'bl', weight: 'id', text: { expr: 'item.id' } },
  ],
  tints,
  glyph: { hook: 'glyph' },
  mark: { hook: 'mark' },
  hooks: {
    category: (cell) => categoryOf(cell),
    years: (cell) => yearRange(cell.year_from, cell.year_to, isRetired(cell)),
    glyph: (cell) => glyphFor(cell, Infinity) ?? null,
    mark: (cell) => markFor(cell) ?? null,
  },
};
