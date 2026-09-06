export type CellState =
  'unknown' | 'timeout' | 'failed' | 'defect' | 'problemElsewhere' | 'defectElsewhere';

export interface CellStyle {
  fill: string;
  /** null means the state gets no border at all -- the unknown field colour
   *  recedes rather than competing with everything drawn on top of it. */
  border: string | null;
  weight: 'thick' | 'thin' | null;
}

export type Palette = Record<CellState, CellStyle>;

// Lightness is reserved for "has been rendered" -- a rendered thumbnail is
// the brightest thing on the wall, so a problem fill has to stay dark enough
// to sit in the gray field. The border carries the state instead, brighter
// and more saturated than the fill it sits on. Tuned by eye over two rounds;
// none of the six values coincides with a `--wzl-*` token, so they stay
// literal rather than drifting to a close-but-different one.
export const DEFAULT_PALETTE: Palette = {
  unknown: { fill: '#3a3a3f', border: null, weight: null },
  timeout: { fill: '#42302a', border: '#c86a42', weight: 'thick' },
  failed: { fill: '#4a2626', border: '#e03030', weight: 'thick' },
  defect: { fill: '#463a20', border: '#e8a020', weight: 'thick' },
  problemElsewhere: { fill: '#42302a', border: '#c86a42', weight: 'thin' },
  defectElsewhere: { fill: '#463a20', border: '#e8a020', weight: 'thin' },
};

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

const CELL_STATES = Object.keys(DEFAULT_PALETTE) as CellState[];

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
  return out;
}
