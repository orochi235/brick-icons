import { expect, it } from 'vitest';
import { yearRange } from '@lab/corpus/tags';

it('leaves a part still being made without an end year', () => {
  expect(yearRange(1979, 2026, false)).toBe('1979–');
});

it('reads a retired part as the span it was made over', () => {
  expect(yearRange(1958, 1978, true)).toBe('1958–1978');
});

it('reads a part that came and went in one year as that year', () => {
  expect(yearRange(1967, 1967, true)).toBe('1967');
});

it('says nothing about a part the catalogs do not list', () => {
  expect(yearRange(null, null, false)).toBeNull();
});
