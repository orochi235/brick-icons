import { expect, it } from 'vitest';
import { yearRange } from '@lab/corpus/tags';

it('reads a span of years as a range', () => {
  expect(yearRange(1979, 2026)).toBe('1979–2026');
});

it('reads a part that came and went in one year as that year', () => {
  expect(yearRange(1967, 1967)).toBe('1967');
});

it('says nothing about a part the catalogs do not list', () => {
  expect(yearRange(null, null)).toBeNull();
});
