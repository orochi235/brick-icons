import { describe, expect, it } from 'vitest';
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
    const set: WorkingSet = { kind: 'base', moved: true, outOfScope: false,
                              obsolete: false, posed: false,
                              excluded: ['Sticker', 'Minifig'],
                              badges: ['technic', 'popular'] };
    expect(round(set)).toEqual(set);
  });

  it('keeps every excluded category rather than the last one', () => {
    const q = toQuery({ ...DEFAULT_SET, excluded: ['A', 'B'] });
    expect(q.getAll('excluded')).toEqual(['A', 'B']);
  });

  it('leaves obsolete parts out until the address asks for them', () => {
    expect(DEFAULT_SET.obsolete).toBe(false);
    expect(fromQuery(new URLSearchParams('obsolete=true')).obsolete).toBe(true);
  });

  it('falls back to all parts on a kind it does not have', () => {
    expect(fromQuery(new URLSearchParams('kind=rendered')).kind).toBe('all');
  });
});

describe('wallHref', () => {
  it('hands the wall the slot and the same membership', () => {
    const href = wallHref({ ...DEFAULT_SET, outOfScope: false,
                            excluded: ['Sticker'] }, 'silhouette-naive');
    const q = new URLSearchParams(href.slice(href.indexOf('?')));
    expect(href.startsWith('/corpus?')).toBe(true);
    expect(q.get('source')).toBe('silhouette-naive');
    expect(q.get('outOfScope')).toBe('false');
    expect(q.getAll('excluded')).toEqual(['Sticker']);
  });

  it('carries the two newer classes across as well', () => {
    const href = wallHref({ ...DEFAULT_SET, obsolete: false, posed: false },
                          'silhouette-naive');
    const q = new URLSearchParams(href.slice(href.indexOf('?')));
    expect(q.get('obsolete')).toBe('false');
    expect(q.get('posed')).toBe('false');
  });
});
