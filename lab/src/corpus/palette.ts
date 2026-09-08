import { DEFAULT_PARAMS, type ColorParamKey } from '@lab/corpus/params';
import {
  STATES, cssVarTable, labelTable, paramKeys, stateKeys, styleTable,
  type CellStyle, type StateKey,
} from '@lab/corpus/states';

export type { CellStyle } from '@lab/corpus/states';

export type CellState = StateKey;

/** The cell-state fills, plus the chrome the wall draws over them -- the
 *  caret and the band headers are not cell states, so none of them appears
 *  in `CELL_STATES`. */
export type Palette = Record<CellState, CellStyle> & {
  caret: string;
  /** An outer band's header. */
  label: CellStyle;
  /** An inner block's header, which must not compete with it. */
  sublabel: CellStyle;
  /** A part that matched nothing outside. Its own flat tone, so absence never
   *  reads as the low end of a ramp. */
  unmatched: CellStyle;
};

const CELL_PALETTE: Record<CellState, CellStyle> = styleTable();

const CARET_PROPERTY = '--corpus-caret-color';
const LABEL_PROPERTY = '--corpus-label';
const SUBLABEL_PROPERTY = '--corpus-sublabel';
const UNMATCHED_PROPERTY = '--corpus-unmatched';

export const DEFAULT_PALETTE: Palette = {
  ...CELL_PALETTE,
  caret: DEFAULT_PARAMS.caretColor,
  label: { fill: '#e8e8ea', border: null, weight: null },
  sublabel: { fill: '#7e7e88', border: null, weight: null },
  unmatched: { fill: '#2a2a2e', border: null, weight: null },
};

/** The CSS custom property each state's fill and border live in. Exported so
 *  a consumer can name a state's variables without hand-writing them: the
 *  legend's swatches did, and fell four states behind the table. */
export const STATE_CSS_VAR: Record<CellState, { fill: string; border: string | null }> =
  cssVarTable();

const PROPERTY = STATE_CSS_VAR;

/** Where a params panel's color row writes each color param -- the same CSS
 *  custom properties `readPalette` reads, keyed the way `Params` names them
 *  rather than by state, so `useParams` can iterate `COLOR_PARAM_KEYS`
 *  without a state/fill-or-border switch of its own. */
export const PARAM_CSS_VAR: Record<ColorParamKey, string> = {
  ...Object.fromEntries(STATES.flatMap((state) => {
    const param = paramKeys(state);
    const prop = PROPERTY[state.key];
    const rows: [string, string][] = [[param.fill, prop.fill]];
    if (param.border !== null && prop.border !== null) rows.push([param.border, prop.border]);
    return rows;
  })),
  caretColor: CARET_PROPERTY,
} as Record<ColorParamKey, string>;

/** Legend order, which is not match order -- see `states.ts`. Every table
 *  keyed by state iterates this. */
export const CELL_STATES: CellState[] = stateKeys();

/** What each state is called on the legend. */
export const STATE_LABEL: Record<CellState, string> = labelTable();

function readVar(styles: CSSStyleDeclaration, prop: string, fallback: string): string {
  const value = styles.getPropertyValue(prop).trim();
  return value.length > 0 ? value : fallback;
}

/** Reads the wall's cell-state colors from CSS custom properties on
 *  `el`, falling back to the tuned defaults for anything the stylesheet
 *  doesn't declare. These are canvas fills, so CSS cannot reach them any
 *  other way -- this is how the wall's colors track a theme change. */
export function readPalette(el: Element): Palette {
  const styles = getComputedStyle(el);
  const out = {} as Palette;
  for (const state of CELL_STATES) {
    const prop = PROPERTY[state];
    const fallback = DEFAULT_PALETTE[state];
    const fill = readVar(styles, prop.fill, fallback.fill);
    const border = prop.border ? readVar(styles, prop.border, fallback.border as string) : null;
    out[state] = { fill, border, weight: fallback.weight };
  }
  out.caret = readVar(styles, CARET_PROPERTY, DEFAULT_PALETTE.caret);
  out.label = { fill: readVar(styles, LABEL_PROPERTY, DEFAULT_PALETTE.label.fill),
                border: null, weight: null };
  out.sublabel = { fill: readVar(styles, SUBLABEL_PROPERTY, DEFAULT_PALETTE.sublabel.fill),
                   border: null, weight: null };
  out.unmatched = { fill: readVar(styles, UNMATCHED_PROPERTY, DEFAULT_PALETTE.unmatched.fill),
                    border: null, weight: null };
  return out;
}
