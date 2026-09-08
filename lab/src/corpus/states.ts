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
  review_defects: number;
  accepted_defects: number;
  error: string | null;
  /** The condition keys that hold in a slot other than the one being drawn.
   *  The server decides, because only it can see the other slots. */
  elsewhere: readonly string[];
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
// ONE ROW PER CONDITION. The "in another slot" variant of each is derived
// below and never written here: hand-writing the pair is how `problemElsewhere`
// came to wear the blue of `timeout` while standing for `failed`.
const CONDITIONS = [
  { key: 'unknown', label: 'unknown',
    fill: '#3a3a3f', border: null, weight: null, sibling: false,
    precedence: 1000, match: () => true },
  // Borderless like `unknown`, and light where every other state is dark: the
  // cell is drawn as a small circle, so it is a mark rather than a field and
  // cannot be mistaken for a rendered thumbnail.
  // Ahead of every problem state: a part the project is not drawing yet has
  // not failed at anything, and a wall of red stickers would say it had.
  // A part is out of scope everywhere or nowhere, so there is no sibling.
  { key: 'outOfScope', label: 'currently out of scope',
    fill: '#b2a3dd', border: null, weight: null, sibling: false,
    precedence: 10, match: (f: StateFacts) => f.out_of_scope },
  // Above `defect` on purpose. Below it, a part carrying three other faults
  // stays plain gold and nobody ever learns that the fourth was redrawn --
  // which is the whole of what this state exists to say.
  { key: 'review', label: 'fix claimed, needs a look',
    fill: '#3a2740', border: '#d070c0', weight: 'thick', sibling: true,
    precedence: 15, match: (f: StateFacts) => f.review_defects > 0 },
  { key: 'defect', label: 'open defect',
    fill: '#453c27', border: '#daa520', weight: 'thick', sibling: true,
    precedence: 20, match: (f: StateFacts) => f.open_defects > 0 },
  { key: 'timeout', label: 'timed out',
    fill: '#26383f', border: '#30b0d0', weight: 'thick', sibling: true,
    precedence: 30, match: (f: StateFacts) => f.error === 'TimeoutError' },
  { key: 'failed', label: 'render error',
    fill: '#4a2626', border: '#e03030', weight: 'thick', sibling: true,
    precedence: 40, match: (f: StateFacts) => f.error !== null },
  // Thin, because nothing here needs doing: the fault is known and the
  // decision was to keep it. No sibling -- a fault someone accepted in
  // another slot says nothing about this one, which is also why
  // `cells.tally_defects` counts it only where it was filed.
  { key: 'accepted', label: 'known issue, not fixing',
    fill: '#26382c', border: '#6f9e78', weight: 'thin', sibling: false,
    precedence: 50, match: (f: StateFacts) => f.accepted_defects > 0 },
] as const;

type Condition = (typeof CONDITIONS)[number];
type SiblingKey = Extract<Condition, { sibling: true }>['key'];

/** Every state this wall can color a cell: a condition, or the same condition
 *  seen in another slot. Derived, so a new row above widens the palette, the
 *  params panel, the legend and the CSS variables with nothing else told. */
export type StateKey = Condition['key'] | `${SiblingKey}Elsewhere`;

/** The states that have a border, and so a border color to name. Every
 *  sibling has one by construction; among the conditions only some do. */
export type BorderedKey =
  | Extract<Condition, { border: string }>['key']
  | `${SiblingKey}Elsewhere`;

// How far below its own condition an "in another slot" state ranks. Wide
// enough that every sibling sorts under every condition except `accepted`,
// which is where `defectElsewhere` already sat.
const ELSEWHERE_DROP = 40;

// The elsewhere border is the condition's border at this saturation and
// lightness, hue untouched -- weaker, same fact. Measured off the two that
// were written by hand: gold #daa520 -> #c7b78f is S 0.33 / L 0.67, cyan
// #30b0d0 -> #97bcc5 is S 0.28 / L 0.68.
const ELSEWHERE_S = 0.30;
const ELSEWHERE_L = 0.675;

function hueOf(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as
    [number, number, number];
  const max = Math.max(r, g, b);
  const span = max - Math.min(r, g, b);
  if (span === 0) return 0;
  const h = max === r ? (g - b) / span + (g < b ? 6 : 0)
    : max === g ? (b - r) / span + 2
    : (r - g) / span + 4;
  return h / 6;
}

/** Hue kept, saturation and lightness replaced -- HSL to hex without a
 *  dependency, and only ever called at module load. */
export function washOut(hex: string, s = ELSEWHERE_S, l = ELSEWHERE_L): string {
  const h = hueOf(hex);
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h * 6) % 2) - 1));
  const m = l - c / 2;
  const wheel: [number, number, number][] = [
    [c, x, 0], [x, c, 0], [0, c, x], [0, x, c], [x, 0, c], [c, 0, x]];
  const [r, g, b] = wheel[Math.floor(h * 6) % 6]!;
  return '#' + [r, g, b].map((v) =>
    Math.round((v + m) * 255).toString(16).padStart(2, '0')).join('');
}

function elsewhereOf(c: Condition & { border: string }): StateSpec {
  return {
    key: `${c.key}Elsewhere`,
    label: `${c.label}, in another slot`,
    fill: c.fill,
    border: washOut(c.border),
    weight: 'thin',
    precedence: c.precedence + ELSEWHERE_DROP,
    match: (f: StateFacts) => f.elsewhere.includes(c.key),
  };
}

/** Listed in legend order: every condition, then every sibling in the same
 *  order. `precedence` is what matching reads, and it is spaced so a new
 *  condition can be ranked without renumbering its neighbours. */
export const STATES: readonly (StateSpec & { key: StateKey })[] = [
  ...CONDITIONS.map((c) => ({ ...c }) as StateSpec & { key: StateKey }),
  ...CONDITIONS.filter((c): c is Condition & { border: string; sibling: true } =>
    c.sibling && c.border !== null)
    .map((c) => elsewhereOf(c) as StateSpec & { key: StateKey }),
];

/** The order `cellState` tries the predicates in, sorted once here rather
 *  than per cell. */
export const BY_PRECEDENCE: readonly (StateSpec & { key: StateKey })[] =
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
