import { expect, it } from 'vitest';
import { defectId, engineFor } from '@lab/corpus/flag';

it('names the engine behind a facet slot, not the facet', () => {
  expect(engineFor('white-naive')).toBe('naive');
  expect(engineFor('silhouette-occt')).toBe('occt');
  expect(engineFor('naive')).toBe('naive');
});

it('reads a filed defect id the way the hand-written ones read', () => {
  expect(defectId('4524', 'a circle whose visible part is several arcs is drawn whole'))
    .toBe('4524-a-circle-whose-visible-part');
});

it('falls back to the part alone when the title slugs to nothing', () => {
  expect(defectId('3001', '???')).toBe('3001');
});

it('reads the engine off a slot whose qualifier is not the census', () => {
  expect(engineFor('translucent-naive')).toBe('naive');
  expect(engineFor('translucent-occt')).toBe('occt');
  expect(engineFor('ldview')).toBe('ldview');
});
