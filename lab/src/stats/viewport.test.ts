import { describe, expect, it } from 'vitest';
import { DEFAULT_VIEWPORT, fromHash, toHash } from '@lab/stats/viewport';

describe('viewport', () => {
  it('carries nothing when there is nothing to carry', () => {
    expect(toHash(DEFAULT_VIEWPORT)).toBe('');
  });

  it('round-trips where the reader was and what they turned off', () => {
    const view = { y: 1280, hide: ['drawn', 'timeout'], hidePhase: ['fill'] };
    expect(fromHash(`#${toHash(view)}`)).toEqual(view);
  });

  it('rounds the scroll offset: a fractional pixel is not a position', () => {
    expect(toHash({ ...DEFAULT_VIEWPORT, y: 40.1875 })).toBe('y=40');
  });

  it('reads a hash someone typed as the default rather than throwing the '
     + 'page away', () => {
    expect(fromHash('#y=banana')).toEqual(DEFAULT_VIEWPORT);
    expect(fromHash('#y=-9')).toEqual(DEFAULT_VIEWPORT);
    expect(fromHash('')).toEqual(DEFAULT_VIEWPORT);
    expect(fromHash('#hide=,,')).toEqual(DEFAULT_VIEWPORT);
  });

  it('takes a hash with or without its #', () => {
    expect(fromHash('y=12').y).toBe(12);
    expect(fromHash('#y=12').y).toBe(12);
  });
});
