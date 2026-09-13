import { describe, expect, it } from 'vitest';
import { CLASS_SPECS } from '@lab/corpus/criteria';
import { readWallLink } from '@lab/corpus/wallHash';
import { DEFAULT_SET, fromQuery, toQuery, wallHref,
         type WorkingSet } from '@lab/stats/workingSet';

const round = (set: WorkingSet) => fromQuery(toQuery(set));

describe('the working set in the address bar', () => {
  it('says nothing at all about a default set', () => {
    expect(toQuery(DEFAULT_SET).toString()).toBe('');
  });

  it('reads a bare address as the default set', () => {
    expect(fromQuery(new URLSearchParams())).toEqual(DEFAULT_SET);
  });

  it('survives the round trip', () => {
    const set: WorkingSet = { kind: 'base',
                              shown: { moved: true, outOfScope: false,
                                       obsolete: true, posed: false },
                              excluded: ['Sticker', 'Minifig'],
                              badges: ['technic', 'popular'] };
    expect(round(set)).toEqual(set);
  });

  it('names a class only where it departs from the default', () => {
    const q = toQuery({ ...DEFAULT_SET,
                        shown: { ...DEFAULT_SET.shown, moved: true, posed: false } });
    expect(q.getAll('show')).toEqual(['moved']);
    expect(q.getAll('hide')).toEqual(['posed']);
  });

  it('writes every class the wall has, however the table grows', () => {
    for (const { key } of CLASS_SPECS) {
      const flipped = { ...DEFAULT_SET,
                        shown: { ...DEFAULT_SET.shown, [key]: !DEFAULT_SET.shown[key] } };
      expect(toQuery(flipped).toString(), key).not.toBe('');
      expect(round(flipped)).toEqual(flipped);
    }
  });

  it('keeps every excluded category rather than the last one', () => {
    const q = toQuery({ ...DEFAULT_SET, excluded: ['A', 'B'] });
    expect(q.getAll('excluded')).toEqual(['A', 'B']);
  });

  it('leaves obsolete parts out until the address asks for them', () => {
    expect(DEFAULT_SET.shown.obsolete).toBe(false);
    expect(fromQuery(new URLSearchParams('show=obsolete')).shown.obsolete).toBe(true);
  });

  it('ignores a class it does not have', () => {
    expect(fromQuery(new URLSearchParams('hide=retired'))).toEqual(DEFAULT_SET);
  });

  it('falls back to all parts on a kind it does not have', () => {
    expect(fromQuery(new URLSearchParams('kind=rendered')).kind).toBe('all');
  });
});

describe('wallHref', () => {
  it('hands the wall the slot and the same membership', () => {
    const href = wallHref({ ...DEFAULT_SET,
                            shown: { ...DEFAULT_SET.shown, outOfScope: false },
                            excluded: ['Sticker'] }, 'silhouette-naive');
    const q = new URLSearchParams(href.slice(href.indexOf('?')));
    expect(href.startsWith('/corpus?')).toBe(true);
    expect(q.get('source')).toBe('silhouette-naive');
    expect(q.get('outOfScope')).toBe('false');
    expect(q.getAll('excluded')).toEqual(['Sticker']);
  });

  it('carries the two newer classes across as well', () => {
    const href = wallHref({ ...DEFAULT_SET,
                            shown: { ...DEFAULT_SET.shown, obsolete: false, posed: false } },
                          'silhouette-naive');
    const q = new URLSearchParams(href.slice(href.indexOf('?')));
    expect(q.get('obsolete')).toBe('false');
    expect(q.get('posed')).toBe('false');
  });

  it('is read back by the wall as the same parts', () => {
    const set: WorkingSet = { kind: 'printed',
                              shown: { moved: true, outOfScope: false,
                                       obsolete: false, posed: true },
                              excluded: ['Sticker'], badges: ['technic'] };
    const href = wallHref(set, 'occt');
    expect(readWallLink(href.slice(href.indexOf('?')))).toEqual({
      source: 'occt', filter: 'printed', shown: set.shown,
      excluded: ['Sticker'], badges: ['technic'],
    });
  });
});
