import { describe, expect, it } from 'vitest';

import { naturalCompare } from '@lab/corpus/natural';

const sorted = (ids: string[]) => ids.slice().sort(naturalCompare);

describe('naturalCompare', () => {
  it('orders a digit run by its value, not its first character', () => {
    expect(sorted(['10247', '2', '1', '9', '3001'])).toEqual(
      ['1', '2', '9', '3001', '10247']);
  });

  it('keeps a bare id ahead of its own mould variants', () => {
    expect(sorted(['3001b', '3001', '3001a', '3002'])).toEqual(
      ['3001', '3001a', '3001b', '3002']);
  });

  it('compares each component in turn, not one digit', () => {
    expect(sorted(['3068bp01', '3068bp0a', '3068bp2', '3068bp10'])).toEqual(
      ['3068bp0a', '3068bp01', '3068bp2', '3068bp10']);
  });

  it('leaves a sigil after every letter, as the category sort needs', () => {
    expect(sorted(['~Brick', 'Plate', 'Brick'])).toEqual(
      ['Brick', 'Plate', '~Brick']);
  });

  it('reads a leading-zero run as its value', () => {
    expect(naturalCompare('4740p03', '4740p3')).toBe(0);
    expect(sorted(['4740p010', '4740p03'])).toEqual(['4740p03', '4740p010']);
  });

  it('orders an unofficial id by the number inside it', () => {
    expect(sorted(['u9095', 'u910', 'u9'])).toEqual(['u9', 'u910', 'u9095']);
  });
});
