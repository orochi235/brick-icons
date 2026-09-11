import { describe, expect, it } from 'vitest';
import { RAMP_NAMES, TINT_MODES, ramp, tintFor } from '@lab/corpus/tint';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import type { Cell } from '@lab/corpus/types';

const c = (over: Partial<Cell>): Cell => ({
  id: 'x', index: 0, title: '', category: null, family: null, printed: false,
  obsolete: false, base: false, out_of_scope: false, moved: false,
  year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [], ...over,
});

describe('ramp', () => {
  it('clamps at both ends', () => {
    expect(ramp(-1)).toBe(ramp(0));
    expect(ramp(2)).toBe(ramp(1));
  });
});

describe('tintFor', () => {
  it('gives an unmatched part the unmatched style, never the ramp\'s floor', () => {
    const style = tintFor(c({}), 'sets', DEFAULT_PALETTE);
    expect(style).toBe(DEFAULT_PALETTE.unmatched);
    expect(style).not.toBe(tintFor(c({ sets: 1 }), 'sets', DEFAULT_PALETTE));
  });

  it('separates a part in one set from one in nine thousand', () => {
    expect(tintFor(c({ sets: 1 }), 'sets', DEFAULT_PALETTE).fill)
      .not.toBe(tintFor(c({ sets: 8953 }), 'sets', DEFAULT_PALETTE).fill);
  });

  it('is logarithmic, so a tenth of the range is high on the ramp, not low', () => {
    const tenth = tintFor(c({ sets: 895 }), 'sets', DEFAULT_PALETTE).fill;
    // A linear scale would put a tenth just off the floor; a log one puts it
    // three quarters of the way up.
    expect(tenth).toBe(ramp(0.75));
    expect(tenth).not.toBe(ramp(0.1));
  });

  it('separates the oldest part in the catalog from the newest', () => {
    expect(tintFor(c({ year_from: 1954 }), 'year', DEFAULT_PALETTE).fill)
      .not.toBe(tintFor(c({ year_from: 2027 }), 'year', DEFAULT_PALETTE).fill);
  });

  it('gives an undated part the unmatched style, not the ramp\'s floor', () => {
    expect(tintFor(c({ sets: 3 }), 'year', DEFAULT_PALETTE))
      .toBe(DEFAULT_PALETTE.unmatched);
  });

  it('falls back to the status palette in status mode', () => {
    expect(tintFor(c({ open_defects: 1 }), 'status', DEFAULT_PALETTE))
      .toBe(DEFAULT_PALETTE.defect);
  });

  it('gives a part with no colour count the unmatched style', () => {
    expect(tintFor(c({ sets: 3 }), 'colors', DEFAULT_PALETTE))
      .toBe(DEFAULT_PALETTE.unmatched);
  });

  it('separates a one-colour part from the most colourful one', () => {
    expect(tintFor(c({ colors: 1 }), 'colors', DEFAULT_PALETTE).fill)
      .not.toBe(tintFor(c({ colors: 81 }), 'colors', DEFAULT_PALETTE).fill);
  });

  it('lifts the median colour count off the floor, which a linear ramp would not', () => {
    // The median part is in 4 colours; log puts that a third of the way up.
    const median = tintFor(c({ colors: 4 }), 'colors', DEFAULT_PALETTE).fill;
    expect(median).not.toBe(ramp(0));
    expect(median).toBe(ramp(Math.log10(4) / Math.log10(81)));
  });

  it('names every mode it supports', () => {
    expect(TINT_MODES).toEqual(['status', 'secs', 'year', 'sets', 'colors']);
  });

  it('logs render seconds, which a linear ramp cannot show', () => {
    // Measured over 68,827 occt timings: median 6.1s, p99 202.7s. A linear
    // ramp leaves 98% of the wall in its bottom two shades, a log one 36%.
    const at = (secs: number) => tintFor(c({ secs }), 'secs', DEFAULT_PALETTE).fill;
    expect(at(6.1)).not.toBe(at(64.5));
    expect(at(64.5)).not.toBe(at(202.7));
    // Under a second pins to the floor rather than going negative.
    expect(at(0.2)).toBe(at(1));
  });

  it('gives a cell with no timing the unmatched swatch, not the floor', () => {
    expect(tintFor(c({ secs: null }), 'secs', DEFAULT_PALETTE))
      .toBe(DEFAULT_PALETTE.unmatched);
  });

  it('draws the same value differently in each gradient', () => {
    expect(ramp(0.5, 'ice')).not.toBe(ramp(0.5, 'ember'));
    expect(ramp(0.5, 'viridis')).not.toBe(ramp(0.5, 'ember'));
  });

  it('runs every gradient dark to light, since these encode magnitude', () => {
    const lum = (colour: string) => {
      const [r, g, b] = colour.match(/\d+/g)!.map(Number);
      return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
    };
    for (const name of RAMP_NAMES) {
      expect(lum(ramp(1, name))).toBeGreaterThan(lum(ramp(0, name)));
    }
  });

  it('clamps every gradient at both ends, not just the default', () => {
    for (const name of RAMP_NAMES) {
      expect(ramp(-1, name)).toBe(ramp(0, name));
      expect(ramp(2, name)).toBe(ramp(1, name));
    }
  });

  it('names every mode it supports', () => {
    expect(TINT_MODES).toEqual(['status', 'secs', 'year', 'sets', 'colors']);
  });
});
