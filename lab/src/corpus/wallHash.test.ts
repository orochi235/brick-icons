import { describe, expect, it } from 'vitest';
import { readWallHash, readWallLink, wallHashString, wallLinkQuery }
  from '@lab/corpus/wallHash';

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

describe('the whole wall in the hash', () => {
  const full = {
    source: 'occt', part: '3001', cam: { x: 1240, y: 880, scale: 2.4 },
    caret: '3003', sort: 'year' as const, filter: 'printed' as const,
    shown: { moved: true, outOfScope: true, obsolete: false, posed: true },
    grouping: 'category' as const, tint: 'secs' as const,
    gradient: 'ironbow' as const, desc: false,
    excluded: ['Sticker', '|'], badges: ['technic'],
  };

  it('round-trips in the readable spelling', () => {
    const text = wallHashString(full);
    expect(text).not.toContain('w=');
    expect(readWallHash(text)).toEqual(full);
  });

  it('round-trips in the condensed spelling', () => {
    const text = wallHashString(full, true);
    expect(text).toMatch(/^#w=[A-Za-z0-9_-]+$/);
    expect(readWallHash(text)).toEqual(full);
  });

  it('spells the camera rounded, so a pan does not write noise', () => {
    expect(wallHashString({ cam: { x: 1240.4, y: 880.6, scale: 2.41234 } }))
      .toBe('#cam=1240,881,2.412');
  });

  it('leaves every field at its default out of both spellings', () => {
    const defaults = {
      sort: 'id' as const, filter: 'all' as const, grouping: 'none' as const,
      tint: 'status' as const, gradient: 'ember' as const, desc: true,
      shown: { moved: false, outOfScope: true, obsolete: true, posed: true },
      excluded: [], badges: [],
    };
    expect(wallHashString(defaults)).toBe('');
    expect(wallHashString(defaults, true)).toBe('');
  });

  it('still reads a link written before the hash carried more', () => {
    expect(readWallHash('#source=occt&part=3001'))
      .toEqual({ source: 'occt', part: '3001' });
  });

  it('drops a value it does not recognize back to the default', () => {
    expect(readWallHash('#sort=bogus&filter=nope&group=x&desc=maybe&cam=1,2'))
      .toEqual({});
    expect(readWallHash('#shown=moved,flying')).toEqual(
      { shown: { moved: true, outOfScope: false, obsolete: false, posed: false } });
    expect(readWallHash('#caret=%3Cimg%3E&cam=1,2,-3')).toEqual({});
  });

  it('caps the opaque lists rather than trusting their size', () => {
    const many = Array.from({ length: 200 }, (_, i) => `c${i}`).join(',');
    const read = readWallHash(`#excl=${many},${'y'.repeat(300)}`);
    expect(read.excluded!.length).toBeLessThanOrEqual(64);
    expect(read.excluded!.every((name) => name.length <= 80)).toBe(true);
  });

  it('reads nothing from a condensed hash it did not write', () => {
    expect(readWallHash('#w=!!!')).toEqual({});
    expect(readWallHash('#w=bm90IGpzb24')).toEqual({});
  });
});

describe('readWallLink', () => {
  it('round-trips what it wrote', () => {
    const link = { source: 'occt', filter: 'printed' as const,
                   shown: { moved: true, obsolete: false },
                   excluded: ['Sticker', 'Minifig'], badges: ['technic'] };
    expect(readWallLink(`?${wallLinkQuery(link)}`)).toEqual(link);
  });

  it('reads nothing from a bare address', () => {
    expect(readWallLink('')).toEqual({});
  });

  it('drops a filter, a class value or a slot it does not recognize', () => {
    expect(readWallLink('?filter=everything&posed=maybe&source=%3Cimg%3E'))
      .toEqual({});
  });
});
