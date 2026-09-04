import { describe, expect, it } from 'vitest';
import { defectId, slug } from '@lab/defects/identity';

describe('slug', () => {
  it('lowercases and hyphenates', () => {
    expect(slug('Borehole rim not drawn')).toBe('borehole-rim-not-drawn');
  });

  it('drops punctuation', () => {
    expect(slug('the "near" lip, missing')).toBe('the-near-lip-missing');
  });

  it('collapses runs of separators', () => {
    expect(slug('a   b -- c')).toBe('a-b-c');
  });

  it('truncates on a word boundary', () => {
    const long = 'one two three four five six seven eight nine ten eleven';
    expect(slug(long).length).toBeLessThanOrEqual(40);
    expect(slug(long)).not.toMatch(/-$/);
    expect(slug(long)).toBe('one-two-three-four-five-six-seven-eight');
  });
});

describe('defectId', () => {
  it('joins part, engine and slug', () => {
    expect(defectId('3941', ['occt'], 'borehole rim not drawn', []))
      .toBe('3941-occt-borehole-rim-not-drawn');
  });

  it('names multiple engines in order', () => {
    expect(defectId('3941', ['occt', 'naive'], 'x', []))
      .toBe('3941-naive-occt-x');
  });

  it('uses "both" for every engine at once', () => {
    expect(defectId('3941', ['naive', 'occt'], 'x', [], ['naive', 'occt']))
      .toBe('3941-both-x');
  });

  it('suffixes to avoid colliding with an existing id', () => {
    expect(defectId('3941', ['occt'], 'x', ['3941-occt-x'])).toBe('3941-occt-x-2');
  });

  it('keeps counting past the first collision', () => {
    expect(defectId('3941', ['occt'], 'x', ['3941-occt-x', '3941-occt-x-2']))
      .toBe('3941-occt-x-3');
  });
});
