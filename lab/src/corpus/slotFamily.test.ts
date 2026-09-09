import { expect, it } from 'vitest';
import { facetOf, familiesIn, familyOf, slotIn } from '@lab/corpus/slotFamily';

const ALL = ['naive', 'occt', 'decal', 'ldview', 'reference',
             'translucent-naive', 'translucent-occt',
             'silhouette-naive', 'silhouette-occt',
             'white-naive', 'white-occt'].map((source) => ({ source }));

it('sorts every slot db.SOURCES names into a family', () => {
  const by: Record<string, string[]> = {};
  for (const { source } of ALL) (by[familyOf(source)] ??= []).push(source);
  expect(by).toEqual({
    occt: ['occt', 'translucent-occt', 'silhouette-occt', 'white-occt'],
    legacy: ['naive', 'translucent-naive', 'silhouette-naive', 'white-naive'],
    reference: ['ldview', 'reference'],
    decal: ['decal'],
  });
});

it('names the bare slot for the drawing it actually is', () => {
  expect(facetOf('naive')).toBe('flat3');
  expect(facetOf('occt')).toBe('flat3');
  expect(facetOf('white-occt')).toBe('white');
  expect(facetOf('translucent-naive')).toBe('translucent');
});

// The two references differ by renderer, not by what they drew, so splitting
// a facet off them would leave both called the same thing.
it('keeps a reference slot whole', () => {
  expect(facetOf('ldview')).toBe('ldview');
  expect(facetOf('reference')).toBe('reference');
});

it('offers only the families something has been drawn in', () => {
  expect(familiesIn([{ source: 'occt' }, { source: 'white-occt' }])).toEqual(['occt']);
  expect(familiesIn(ALL)).toEqual(['occt', 'legacy', 'reference', 'decal']);
});

it('holds the facet across a family change', () => {
  expect(slotIn(ALL, 'occt', 'silhouette')).toBe('silhouette-occt');
  expect(slotIn(ALL, 'legacy', 'white')).toBe('white-naive');
});

// Population order comes from the route, so the first slot in a family is the
// one with the most renders -- the right landing place when nothing matches.
it('falls back to a family first slot when the facet has no counterpart', () => {
  expect(slotIn(ALL, 'decal', 'silhouette')).toBe('decal');
  expect(slotIn([{ source: 'occt' }, { source: 'white-occt' }], 'occt', 'nothing'))
    .toBe('occt');
});

it('reports no slot for a family nothing was drawn in', () => {
  expect(slotIn([{ source: 'occt' }], 'legacy', 'flat3')).toBeNull();
});
