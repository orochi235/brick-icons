import { describe, expect, it } from 'vitest';
import type { LdrawColor } from '@lab/api/types';
import { familyLabel, matchColors, swatchFor } from '@lab/config/colorMatch';

const PALETTE: LdrawColor[] = [
  { code: 0, name: 'Black', hex: '#1b2a34', alpha: 255, category: 'Solid', legoId: 1 },
  { code: 4, name: 'Red', hex: '#b40000', alpha: 255, category: 'Solid', legoId: 1 },
  { code: 71, name: 'Light Bluish Grey', hex: '#969696', alpha: 255, category: 'Solid', legoId: 1 },
  { code: 72, name: 'Dark Bluish Grey', hex: '#6c6e68', alpha: 255, category: 'Solid', legoId: 1 },
  { code: 36, name: 'Trans Red', hex: '#c91a09', alpha: 128, category: 'Transparent', legoId: 2 },
];

describe('matchColors', () => {
  it('offers the whole palette for an empty field', () => {
    expect(matchColors(PALETTE, '')).toHaveLength(PALETTE.length);
  });

  it('matches a name case-insensitively, anywhere in it', () => {
    expect(matchColors(PALETTE, 'bluish').map((c) => c.code)).toEqual([71, 72]);
  });

  it('folds the separators a typist leaves out', () => {
    expect(matchColors(PALETTE, 'lightbluish').map((c) => c.code)).toEqual([71]);
  });

  // LDConfig spells it British; the CLI resolves both, so the field must too.
  it('resolves the gray/grey split either way', () => {
    expect(matchColors(PALETTE, 'dark bluish gray').map((c) => c.code)).toEqual([72]);
  });

  it('matches a code exactly, not as a substring', () => {
    expect(matchColors(PALETTE, '4').map((c) => c.code)).toEqual([4]);
    expect(matchColors(PALETTE, '7').map((c) => c.code)).toEqual([]);
  });

  it('puts a code match first when a name also matches the digits', () => {
    const pal = [...PALETTE, { code: 5, name: 'Color 71 Lookalike', hex: '#fff', alpha: 255, category: 'Solid', legoId: 3 }];
    expect(matchColors(pal, '71')[0]?.code).toBe(71);
  });

  it('offers nothing for hex, which needs no lookup', () => {
    expect(matchColors(PALETTE, '#b40000')).toEqual([]);
    expect(matchColors(PALETTE, 'b40000')).toEqual([]);
  });

});

describe('swatchFor', () => {
  it('is the color itself when it is opaque', () => {
    expect(swatchFor(PALETTE[0]!)).toBe('#1b2a34');
  });

  // A transparent color drawn opaque reads as a different color entirely.
  it('carries alpha as an eight-digit hex when it is not', () => {
    expect(swatchFor(PALETTE[4]!)).toBe('#c91a0980');
  });
});

describe('matchColors ranking', () => {
  const of = (code: number, name: string, category: string) =>
    ({ code, name, hex: '#888888', alpha: 255, category, legoId: code });

  it('offers every match, not a page of them', () => {
    const many = Array.from({ length: 60 }, (_, i) => of(i + 1, `Grey ${i}`, 'Solid'));
    expect(matchColors(many, 'grey')).toHaveLength(60);
  });

  // A part is moulded in a plastic colour; rubber, Modulex and the retired
  // list are what you scroll past to reach one.
  it('leads with the families a part is actually moulded in', () => {
    const pal = [of(1, 'Rubber Grey', 'Rubber'), of(2, 'Old Grey', 'Obsolete'),
                 of(3, 'Plain Grey', 'Solid'), of(4, 'Shiny Grey', 'Metallic')];
    expect(matchColors(pal, 'grey').map((c) => c.code)).toEqual([3, 4, 1, 2]);
  });

  it('sinks the internal material colors below everything real', () => {
    const pal = [of(1, 'Main Grey', 'Internal Common Material'), of(2, 'Grey', 'Modulex')];
    expect(matchColors(pal, 'grey').map((c) => c.code)).toEqual([2, 1]);
  });

  it('keeps the palette order inside one family', () => {
    const pal = [of(7, 'Grey B', 'Solid'), of(3, 'Grey A', 'Solid')];
    expect(matchColors(pal, 'grey').map((c) => c.code)).toEqual([7, 3]);
  });

  it('still puts an exact code first, whatever family it is in', () => {
    const pal = [of(3, 'Plain Grey', 'Solid'), of(256, 'Rubber Black', 'Rubber')];
    expect(matchColors(pal, '256')[0]?.code).toBe(256);
  });
});

describe('familyLabel', () => {
  it('drops the words that say nothing at a glance', () => {
    expect(familyLabel('Pearlescent Plastic')).toBe('pearl');
    expect(familyLabel('Metallic Paint')).toBe('metallic');
    expect(familyLabel('Chrome Plated')).toBe('chrome');
    expect(familyLabel('Internal Common Material')).toBe('internal');
  });

  // Solid is the default a reader assumes; saying so on 200 rows is noise.
  it('says nothing for the family that needs no saying', () => {
    expect(familyLabel('Solid')).toBe('');
    expect(familyLabel('')).toBe('');
  });

  it('keeps a family it has no shorter name for', () => {
    expect(familyLabel('Speckle')).toBe('speckle');
    expect(familyLabel('Modulex')).toBe('modulex');
  });
});

describe('matchColors palette width', () => {
  const of = (code: number, name: string, legoId: number | null, category = 'Solid') =>
    ({ code, name, hex: '#888888', alpha: 255, category, legoId });

  // LDConfig numbers the colors LEGO itself moulds; the rest are LDraw-only
  // entries, and offering 322 of them by default buries the 185 that matter.
  it('offers only the colors LEGO numbers unless asked for all of them', () => {
    const pal = [of(1, 'Grey', 26), of(2, 'Grey Derived', null)];
    expect(matchColors(pal, 'grey').map((c) => c.code)).toEqual([1]);
    expect(matchColors(pal, 'grey', true).map((c) => c.code)).toEqual([1, 2]);
  });

  it('applies the same cut with nothing typed', () => {
    const pal = [of(1, 'Grey', 26), of(2, 'Grey Derived', null)];
    expect(matchColors(pal, '')).toHaveLength(1);
    expect(matchColors(pal, '', true)).toHaveLength(2);
  });

  // A code names one exact color; refusing to find it because of a checkbox
  // would make the field lie about what --part-color accepts.
  it('finds an exact code either way', () => {
    const pal = [of(507, 'Obsolete Thing', null, 'Obsolete')];
    expect(matchColors(pal, '507').map((c) => c.code)).toEqual([507]);
  });
});
