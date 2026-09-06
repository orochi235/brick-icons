import { describe, expect, it } from 'vitest';
import { NO_CATEGORY } from '@lab/corpus/facts';
import { familyFacets, familyOf, FAMILIES, OTHER_FAMILY } from '@lab/corpus/families';

describe('familyOf', () => {
  it('places a category under the family that owns it', () => {
    expect(familyOf('Slope')).toBe('Bricks & plates');
    expect(familyOf('Windscreen')).toBe('Vehicles');
    expect(familyOf('Sticker')).toBe('Decoration');
  });

  it('reads the library\'s inconsistent case', () => {
    expect(familyOf('TECHNIC')).toBe('Technic & mechanism');
  });

  it('sends a category nobody placed to the catch-all', () => {
    expect(familyOf('Beehive')).toBe(OTHER_FAMILY);
    expect(familyOf('a category invented next year')).toBe(OTHER_FAMILY);
  });

  it('keeps the rows that name no drawable subject together', () => {
    expect(familyOf('Moved')).toBe('Not a part');
    expect(familyOf(NO_CATEGORY)).toBe('Not a part');
  });
});

describe('familyFacets', () => {
  const counts = new Map([
    ['Brick', 1332], ['Tile', 2117], ['Duplo', 589], ['Beehive', 1],
  ]);

  it('folds categories into their families, biggest member first', () => {
    expect(familyFacets(counts)).toEqual([
      { family: 'Bricks & plates',
        total: 3449,
        members: [{ name: 'Tile', n: 2117 }, { name: 'Brick', n: 1332 }] },
      { family: 'Other themes', total: 589, members: [{ name: 'Duplo', n: 589 }] },
      { family: OTHER_FAMILY, total: 1, members: [{ name: 'Beehive', n: 1 }] },
    ]);
  });

  it('leaves out a family with nothing in this slot', () => {
    const drawn = familyFacets(counts).map((f) => f.family);
    expect(drawn.length).toBeLessThan(FAMILIES.length);
    expect(drawn).not.toContain('Vehicles');
  });

  it('strips the leading sigil before placing a category', () => {
    expect(familyFacets(new Map([['~Technic', 187]]))).toEqual([
      { family: 'Technic & mechanism',
        total: 187,
        members: [{ name: 'Technic', n: 187 }] },
    ]);
  });

  it('draws the families in their declared order, not by size', () => {
    const drawn = familyFacets(new Map([['Duplo', 9000], ['Brick', 1]]))
      .map((f) => f.family);
    expect(drawn).toEqual(['Bricks & plates', 'Other themes']);
  });
});
