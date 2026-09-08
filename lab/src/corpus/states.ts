/** How a cell is drawn: the ground it sits on and the border that carries its
 *  state. */
export interface CellStyle {
  fill: string;
  /** null means the state gets no border at all -- the unknown field color
   *  recedes rather than competing with everything drawn on top of it. */
  border: string | null;
  weight: 'thick' | 'thin' | null;
}

/** Everything a state's `match` may read. A `Cell` satisfies it, and so does
 *  one of a part's slots in the detail view -- which is a cell on a wall
 *  nobody is looking at. Deliberately narrower than `Cell`: it is what a host
 *  outside this project would have to supply, so a predicate that reached
 *  past it would not survive the move. */
export interface StateFacts {
  out_of_scope: boolean;
  open_defects: number;
  error: string | null;
  accepted_defects: number;
  open_defects_elsewhere: number;
  error_elsewhere: boolean;
}

export interface StateSpec extends CellStyle {
  key: string;
  /** What the legend calls it. */
  label: string;
  /** Lower matches first. Listing order and matching order are not the same
   *  order, so both are written down rather than one inferred from the other. */
  precedence: number;
  match: (facts: StateFacts) => boolean;
}

// Lightness is reserved for "has been rendered" -- a rendered thumbnail is
// the brightest thing on the wall, so a problem fill has to stay dark enough
// to sit in the gray field. The border carries the state instead, brighter
// and more saturated than the fill it sits on. Tuned by eye over two rounds;
// none of the values coincides with a `--wzl-*` token, so they stay literal
// rather than drifting to a close-but-different one.
//
// Listed in legend order; `precedence` is spaced so a new state can be given
// a rank without renumbering its neighbours.
export const STATES = [
  { key: 'unknown', label: 'unknown',
    fill: '#3a3a3f', border: null, weight: null,
    precedence: 1000, match: () => true },
  // Borderless like `unknown`, and light where every other state is dark: the
  // cell is drawn as a small circle, so it is a mark rather than a field and
  // cannot be mistaken for a rendered thumbnail.
  // Ahead of every problem state: a part the project is not drawing yet has
  // not failed at anything, and a wall of red stickers would say it had.
  { key: 'outOfScope', label: 'currently out of scope',
    fill: '#b2a3dd', border: null, weight: null,
    precedence: 10, match: (f: StateFacts) => f.out_of_scope },
  { key: 'timeout', label: 'timed out',
    fill: '#26383f', border: '#30b0d0', weight: 'thick',
    precedence: 30, match: (f: StateFacts) => f.error === 'TimeoutError' },
  { key: 'failed', label: 'render error',
    fill: '#4a2626', border: '#e03030', weight: 'thick',
    precedence: 40, match: (f: StateFacts) => f.error !== null },
  { key: 'defect', label: 'open defect',
    fill: '#453c27', border: '#daa520', weight: 'thick',
    precedence: 20, match: (f: StateFacts) => f.open_defects > 0 },
  // Thin, because nothing here needs doing: the fault is known and the
  // decision was to keep it. Below every live fault and above anything
  // happening in another slot: it is this slot's problem, and it is settled.
  { key: 'accepted', label: 'known issue, not fixing',
    fill: '#26382c', border: '#6f9e78', weight: 'thin',
    precedence: 50, match: (f: StateFacts) => f.accepted_defects > 0 },
  { key: 'problemElsewhere', label: 'problem in another slot',
    fill: '#26383f', border: '#97bcc5', weight: 'thin',
    precedence: 70, match: (f: StateFacts) => f.error_elsewhere },
  { key: 'defectElsewhere', label: 'defect in another slot',
    fill: '#453c27', border: '#c7b78f', weight: 'thin',
    precedence: 60, match: (f: StateFacts) => f.open_defects_elsewhere > 0 },
] as const satisfies readonly StateSpec[];

type Spec = (typeof STATES)[number];

/** Every state this wall can color a cell. Derived, so it widens with the
 *  table above and nothing else has to be told. */
export type StateKey = Spec['key'];

/** The order `cellState` tries the predicates in, sorted once here rather
 *  than per cell. */
export const BY_PRECEDENCE: readonly Spec[] =
  [...STATES].sort((a, b) => a.precedence - b.precedence);

export function stateKeys(): StateKey[] {
  return STATES.map((s) => s.key);
}

/** `outOfScope` -> `out-of-scope`, the spelling the stylesheet and the CSS
 *  custom properties already use. */
export function kebabKey(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

export function styleTable(): Record<StateKey, CellStyle> {
  return Object.fromEntries(STATES.map(
    (s) => [s.key, { fill: s.fill, border: s.border, weight: s.weight }],
  )) as Record<StateKey, CellStyle>;
}

export function labelTable(): Record<StateKey, string> {
  return Object.fromEntries(STATES.map((s) => [s.key, s.label])) as Record<StateKey, string>;
}

/** The CSS custom property each of a state's colors is read from and written
 *  to -- `palette.ts` reads them, `useParams` writes them. */
export function cssVarTable(): Record<StateKey, { fill: string; border: string | null }> {
  return Object.fromEntries(STATES.map((s) => [s.key, {
    fill: `--corpus-cell-${kebabKey(s.key)}-fill`,
    border: s.border === null ? null : `--corpus-cell-${kebabKey(s.key)}-border`,
  }])) as Record<StateKey, { fill: string; border: string | null }>;
}

/** What `params.ts` calls a state's colors. */
export function paramKeys(spec: StateSpec): { fill: string; border: string | null } {
  return {
    fill: `${spec.key}Fill`,
    border: spec.border === null ? null : `${spec.key}Border`,
  };
}
