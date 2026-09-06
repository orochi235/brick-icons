import { fillFor } from '@lab/corpus/paint';
import type { CellStyle, Palette } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

export const TINT_MODES = ['status', 'year', 'sets'] as const;
export type TintMode = typeof TINT_MODES[number];

// Quantised, so two cells a few sets apart get the same swatch and a band of
// the ramp reads as a band rather than as noise.
const STEPS = 8;
const LOW = [58, 58, 63];
const HIGH = [232, 196, 120];

export function ramp(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const step = Math.round(clamped * (STEPS - 1)) / (STEPS - 1);
  const rgb = LOW.map((v, i) => Math.round(v + (HIGH[i]! - v) * step));
  return `rgb(${rgb.join(',')})`;
}

// 1954 to 2027, and 8,953 sets -- both from the catalog as it stands, and
// both only affecting where the ramp saturates.
const FIRST_YEAR = 1954;
const YEAR_SPAN = 73;
const MAX_LOG_SETS = Math.log10(8953);

function value(cell: Cell, mode: TintMode): number | null {
  switch (mode) {
    case 'status': return null;
    case 'year': return cell.year_from === null ? null
      : (cell.year_from - FIRST_YEAR) / YEAR_SPAN;
    // Set counts are right-skewed -- a handful of parts are in thousands of
    // sets and most are in a few, so a linear ramp would be one bright cell
    // in a flat floor.
    case 'sets': return cell.sets === null ? null
      : Math.log10(Math.max(1, cell.sets)) / MAX_LOG_SETS;
  }
}

/** A cell's fill under one tint mode.
 *
 *  Only `status` uses the state palette; the rest are ramps over an outside
 *  fact, and a cell with no fact takes `unmatched` rather than the floor. */
export function tintFor(cell: Cell, mode: TintMode, palette: Palette): CellStyle {
  if (mode === 'status') return fillFor(cell, palette);
  const t = value(cell, mode);
  if (t === null) return palette.unmatched;
  return { fill: ramp(t), border: null, weight: null };
}
