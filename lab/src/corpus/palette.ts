import { DEFAULT_PARAMS, type ColorParamKey } from '@lab/corpus/params';

export type CellState =
  'unknown' | 'outOfScope' | 'timeout' | 'failed' | 'defect' | 'problemElsewhere'
  | 'defectElsewhere';

export interface CellStyle {
  fill: string;
  /** null means the state gets no border at all -- the unknown field color
   *  recedes rather than competing with everything drawn on top of it. */
  border: string | null;
  weight: 'thick' | 'thin' | null;
}

/** The cell-state fills, plus the caret's own stroke color -- the caret is UI
 *  chrome, not a cell state, so it never appears in `CELL_STATES`. */
export type Palette = Record<CellState, CellStyle> & { caret: string };

// Lightness is reserved for "has been rendered" -- a rendered thumbnail is
// the brightest thing on the wall, so a problem fill has to stay dark enough
// to sit in the gray field. The border carries the state instead, brighter
// and more saturated than the fill it sits on. Tuned by eye over two rounds;
// none of the six values coincides with a `--wzl-*` token, so they stay
// literal rather than drifting to a close-but-different one. The literals
// themselves live in `params.ts`'s `DEFAULT_PARAMS`, the wall's own params
// panel being the other reader of them.
const CELL_PALETTE: Record<CellState, CellStyle> = {
  unknown: { fill: DEFAULT_PARAMS.unknownFill, border: null, weight: null },
  // Borderless like `unknown`: 2,701 sticker cells in one block would read as
  // a fenced-off region rather than a quiet one.
  outOfScope: { fill: DEFAULT_PARAMS.outOfScopeFill, border: null, weight: null },
  timeout: { fill: DEFAULT_PARAMS.timeoutFill, border: DEFAULT_PARAMS.timeoutBorder,
             weight: 'thick' },
  failed: { fill: DEFAULT_PARAMS.failedFill, border: DEFAULT_PARAMS.failedBorder,
            weight: 'thick' },
  defect: { fill: DEFAULT_PARAMS.defectFill, border: DEFAULT_PARAMS.defectBorder,
            weight: 'thick' },
  problemElsewhere: { fill: DEFAULT_PARAMS.problemElsewhereFill,
                       border: DEFAULT_PARAMS.problemElsewhereBorder, weight: 'thin' },
  defectElsewhere: { fill: DEFAULT_PARAMS.defectElsewhereFill,
                      border: DEFAULT_PARAMS.defectElsewhereBorder, weight: 'thin' },
};

const CARET_PROPERTY = '--corpus-caret-color';

export const DEFAULT_PALETTE: Palette = { ...CELL_PALETTE, caret: DEFAULT_PARAMS.caretColor };

const PROPERTY: Record<CellState, { fill: string; border: string | null }> = {
  unknown: { fill: '--corpus-cell-unknown-fill', border: null },
  outOfScope: { fill: '--corpus-cell-out-of-scope-fill', border: null },
  timeout: { fill: '--corpus-cell-timeout-fill', border: '--corpus-cell-timeout-border' },
  failed: { fill: '--corpus-cell-failed-fill', border: '--corpus-cell-failed-border' },
  defect: { fill: '--corpus-cell-defect-fill', border: '--corpus-cell-defect-border' },
  problemElsewhere: { fill: '--corpus-cell-problem-elsewhere-fill',
                       border: '--corpus-cell-problem-elsewhere-border' },
  defectElsewhere: { fill: '--corpus-cell-defect-elsewhere-fill',
                      border: '--corpus-cell-defect-elsewhere-border' },
};

/** Where a params panel's color row writes each color param -- the same CSS
 *  custom properties `readPalette` reads, keyed the way `Params` names them
 *  rather than by state, so `useParams` can iterate `COLOR_PARAM_KEYS`
 *  without a state/fill-or-border switch of its own. */
export const PARAM_CSS_VAR: Record<ColorParamKey, string> = {
  unknownFill: PROPERTY.unknown.fill,
  outOfScopeFill: PROPERTY.outOfScope.fill,
  timeoutFill: PROPERTY.timeout.fill,
  timeoutBorder: PROPERTY.timeout.border as string,
  failedFill: PROPERTY.failed.fill,
  failedBorder: PROPERTY.failed.border as string,
  defectFill: PROPERTY.defect.fill,
  defectBorder: PROPERTY.defect.border as string,
  problemElsewhereFill: PROPERTY.problemElsewhere.fill,
  problemElsewhereBorder: PROPERTY.problemElsewhere.border as string,
  defectElsewhereFill: PROPERTY.defectElsewhere.fill,
  defectElsewhereBorder: PROPERTY.defectElsewhere.border as string,
  caretColor: CARET_PROPERTY,
};

/** Iteration order for every table keyed by state -- out of scope, then
 *  worst-here-first and worst-elsewhere, matching `cellState`'s precedence. */
export const CELL_STATES = Object.keys(CELL_PALETTE) as CellState[];

/** What each state is called on the legend. */
export const STATE_LABEL: Record<CellState, string> = {
  unknown: 'unknown',
  outOfScope: 'currently out of scope',
  timeout: 'timed out here',
  failed: 'cannot be drawn here',
  defect: 'open defect here',
  problemElsewhere: 'problem in another slot',
  defectElsewhere: 'defect in another slot',
};

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
  return out;
}
