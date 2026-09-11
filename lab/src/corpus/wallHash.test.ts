import { describe, expect, it } from 'vitest';
import { readWallHash, wallHashString } from '@lab/corpus/wallHash';

describe('readWallHash', () => {
  it('takes the open part and the slot it is drawn from', () => {
    expect(readWallHash('#source=silhouette-occt&part=3001')).toEqual(
      { source: 'silhouette-occt', part: '3001' });
  });

  it('reads a hash with no leading marker, and one that is empty', () => {
    expect(readWallHash('part=3626cp7d')).toEqual({ part: '3626cp7d' });
    expect(readWallHash('')).toEqual({});
    expect(readWallHash('#')).toEqual({});
  });

  it('keeps what it recognizes and drops the rest', () => {
    expect(readWallHash('#part=4740&zoom=3')).toEqual({ part: '4740' });
  });

  it('refuses anything that is not a part id or a slot name', () => {
    // The hash is the one piece of this page's state a stranger can set, and
    // both values are put back into the address bar and used to fetch.
    for (const bad of ['<img src=x>', '../../etc/passwd', 'a b', '',
                       'x'.repeat(200), 'javascript:alert(1)']) {
      expect(readWallHash(`#part=${encodeURIComponent(bad)}`).part)
        .toBeUndefined();
    }
  });
});

describe('wallHashString', () => {
  it('round-trips what it wrote', () => {
    const state = { source: 'silhouette-occt', part: '3001' };
    expect(readWallHash(wallHashString(state))).toEqual(state);
  });

  it('goes empty rather than leaving a bare marker behind', () => {
    // A '#' left in the bar after the lightbox closes is a URL that looks
    // different from the one the reader arrived on.
    expect(wallHashString({})).toBe('');
  });

  it('keeps the slot once the lightbox closes', () => {
    expect(wallHashString({ source: 'silhouette-occt' }))
      .toBe('#source=silhouette-occt');
  });
});

describe('tint in the hash', () => {
  it('carries a measured tint and its ramp', () => {
    expect(wallHashString({ source: 'occt', tint: 'secs', gradient: 'ironbow' }))
      .toBe('#source=occt&tint=secs&gradient=ironbow');
    expect(readWallHash('#source=occt&tint=secs&gradient=ironbow'))
      .toEqual({ source: 'occt', tint: 'secs', gradient: 'ironbow' });
  });

  it('leaves the defaults out, so an untouched wall has a bare bar', () => {
    expect(wallHashString({ tint: 'status', gradient: 'ember' })).toBe('');
    expect(wallHashString({ tint: 'secs', gradient: 'ember' })).toBe('#tint=secs');
  });

  it('drops a ramp that no tint is using', () => {
    expect(wallHashString({ tint: 'status', gradient: 'ironbow' })).toBe('');
  });

  it('refuses a mode or ramp it does not know', () => {
    expect(readWallHash('#tint=heat&gradient=rainbow')).toEqual({});
    expect(readWallHash('#tint=secs&gradient=rainbow')).toEqual({ tint: 'secs' });
  });
});
