export type CellState =
  'unknown' | 'timeout' | 'failed' | 'defect' | 'problemElsewhere' | 'defectElsewhere';

export interface CellStyle {
  fill: string;
  /** null means the state gets no border at all -- the unknown field colour
   *  recedes rather than competing with everything drawn on top of it. */
  border: string | null;
  weight: 'thick' | 'thin' | null;
}

/** The six cell-state fills, plus the caret's own stroke color -- the caret
 *  is UI chrome, not a cell state, so it never appears in `CELL_STATES`. */
export type Palette = Record<CellState, CellStyle> & { caret: string };

// Lightness is reserved for "has been rendered" -- a rendered thumbnail is
// the brightest thing on the wall, so a problem fill has to stay dark enough
// to sit in the gray field. The border carries the state instead, brighter
// and more saturated than the fill it sits on. Tuned by eye over two rounds;
// none of the six values coincides with a `--wzl-*` token, so they stay
// literal rather than drifting to a close-but-different one.
const CELL_PALETTE: Record<CellState, CellStyle> = {
  unknown: { fill: '#3a3a3f', border: null, weight: null },
  timeout: { fill: '#26383f', border: '#30b0d0', weight: 'thick' },
  failed: { fill: '#4a2626', border: '#e03030', weight: 'thick' },
  defect: { fill: '#453c27', border: '#daa520', weight: 'thick' },
  problemElsewhere: { fill: '#26383f', border: '#97bcc5', weight: 'thin' },
  defectElsewhere: { fill: '#453c27', border: '#c7b78f', weight: 'thin' },
};

const CARET_PROPERTY = '--corpus-caret-color';
const CARET_DEFAULT_COLOR = '#ffffff';

export const DEFAULT_PALETTE: Palette = { ...CELL_PALETTE, caret: CARET_DEFAULT_COLOR };

const PROPERTY: Record<CellState, { fill: string; border: string | null }> = {
  unknown: { fill: '--corpus-cell-unknown-fill', border: null },
  timeout: { fill: '--corpus-cell-timeout-fill', border: '--corpus-cell-timeout-border' },
  failed: { fill: '--corpus-cell-failed-fill', border: '--corpus-cell-failed-border' },
  defect: { fill: '--corpus-cell-defect-fill', border: '--corpus-cell-defect-border' },
  problemElsewhere: { fill: '--corpus-cell-problem-elsewhere-fill',
                       border: '--corpus-cell-problem-elsewhere-border' },
  defectElsewhere: { fill: '--corpus-cell-defect-elsewhere-fill',
                      border: '--corpus-cell-defect-elsewhere-border' },
};

/** Iteration order for every table keyed by state -- worst-here-first then
 *  worst-elsewhere, matching `cellState`'s precedence. */
export const CELL_STATES = Object.keys(CELL_PALETTE) as CellState[];

/** What each state is called on the legend. */
export const STATE_LABEL: Record<CellState, string> = {
  unknown: 'unknown',
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

/** Reads the wall's six cell-state colours from CSS custom properties on
 *  `el`, falling back to the tuned defaults for anything the stylesheet
 *  doesn't declare. These are canvas fills, so CSS cannot reach them any
 *  other way -- this is how the wall's colours track a theme change. */
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
