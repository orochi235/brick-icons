import { fillFor } from '@lab/corpus/paint';
import type { CellStyle, Palette } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

export const TINT_MODES = ['status', 'secs', 'year', 'sets', 'colors'] as const;
export type TintMode = typeof TINT_MODES[number];

// Quantised, so two cells a few sets apart get the same swatch and a band of
// the ramp reads as a band rather than as noise.
const STEPS = 8;

/** The gradients a measured mode can be drawn in.
 *
 *  Every one is sequential -- one direction, dark to light -- because these
 *  ramps encode magnitude. A diverging or rainbow scale would invent a
 *  midpoint the data has no opinion about, and read as categories.
 *
 *  `ember` is the original and stays the default. `viridis` and `magma` are
 *  the usual perceptually-uniform pair, carried at eight stops each: equal
 *  steps in the number are equal steps to the eye, which the two-endpoint
 *  ramps only approximate. Both also hold up under every form of color
 *  blindness, which `ember` does not. */
export const RAMPS = {
  ember: ['#3a3a3f', '#e8c478'],
  ice: ['#12233a', '#a9e2f3'],
  moss: ['#16281c', '#b7e07a'],
  viridis: ['#440154', '#472d7b', '#3b528b', '#2c728e',
            '#21918c', '#28ae80', '#5ec962', '#addc30'],
  magma: ['#000004', '#1c1044', '#4f127b', '#812581',
          '#b5367a', '#e55964', '#fb8761', '#fec287'],
} as const;

export const RAMP_NAMES = Object.keys(RAMPS) as (keyof typeof RAMPS)[];
export type RampName = keyof typeof RAMPS;

function hex(value: string): [number, number, number] {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(value)!;
  return [parseInt(m[1]!, 16), parseInt(m[2]!, 16), parseInt(m[3]!, 16)];
}

/** A gradient sampled at `t`, quantised to `STEPS` swatches.
 *
 *  Interpolates between the two stops the step falls between, so a ramp reads
 *  the same whether it was written with two stops or eight. */
export function ramp(t: number, name: RampName = 'ember'): string {
  const stops = RAMPS[name].map(hex);
  const clamped = Math.max(0, Math.min(1, t));
  const step = Math.round(clamped * (STEPS - 1)) / (STEPS - 1);
  const at = step * (stops.length - 1);
  const low = Math.floor(at);
  const high = Math.min(low + 1, stops.length - 1);
  const f = at - low;
  const rgb = stops[low]!.map((v, i) =>
    Math.round(v + (stops[high]![i]! - v) * f));
  return `rgb(${rgb.join(',')})`;
}

// 1954 to 2027, and 8,953 sets -- both from the catalog as it stands, and
// both only affecting where the ramp saturates.
const FIRST_YEAR = 1954;
const YEAR_SPAN = 73;
const MAX_LOG_SETS = Math.log10(8953);
// Measured over the golden's 9,269 dated parts: median 9 colors, p90 63,
// top of the range 80.
const MAX_LOG_COLORS = Math.log10(80);
// Measured over 68,827 occt timings: median 6.1s, p90 64.5s, p99 202.7s,
// slowest 678.4s. Logged for the same reason `sets` is, and harder -- a
// linear ramp leaves 98% of the wall in its bottom two shades, a log one 36%.
const MAX_LOG_SECS = Math.log10(680);

function value(cell: Cell, mode: TintMode): number | null {
  switch (mode) {
    case 'status': return null;
    // A cell's own slot's seconds. Anything under a second pins to the floor,
    // which is 1% of parts.
    case 'secs': return cell.secs === null || cell.secs === undefined ? null
      : Math.log10(Math.max(1, cell.secs)) / MAX_LOG_SECS;
    case 'year': return cell.year_from === null ? null
      : (cell.year_from - FIRST_YEAR) / YEAR_SPAN;
    // Set counts are right-skewed -- a handful of parts are in thousands of
    // sets and most are in a few, so a linear ramp would be one bright cell
    // in a flat floor.
    case 'sets': return cell.sets === null ? null
      : Math.log10(Math.max(1, cell.sets)) / MAX_LOG_SETS;
    // Skewed the same way: a linear ramp leaves 62% of the wall in its bottom
    // two shades, a log one 25%.
    case 'colors': return cell.colors === null ? null
      : Math.log10(Math.max(1, cell.colors)) / MAX_LOG_COLORS;
  }
}

/** A cell's fill under one tint mode.
 *
 *  Only `status` uses the state palette; the rest are ramps over an outside
 *  fact, and a cell with no fact takes `unmatched` rather than the floor. */
export function tintFor(cell: Cell, mode: TintMode, palette: Palette,
                        gradient: RampName = 'ember'): CellStyle {
  if (mode === 'status') return fillFor(cell, palette);
  const t = value(cell, mode);
  if (t === null) return palette.unmatched;
  return { fill: ramp(t, gradient), border: null, weight: null };
}
