import type { LdrawColor } from '@lab/api/types';

const HEX = /^#?[0-9a-f]{3,8}$/i;

/** LDConfig families, in the order a part's moulded color is likely to be in
 *  one. Everything unlisted sits between the plastics and the ones below —
 *  a family LDraw adds is offered, just not promoted. */
const FAMILY_RANK: Record<string, number> = {
  Solid: 0, Transparent: 0,
  Pearlescent: 1, 'Pearlescent Plastic': 1, Metallic: 1, 'Metallic Paint': 1,
  Chrome: 1, 'Chrome Plated': 1, Fluorescent: 1, 'Fluorescent Paint': 1,
  Milky: 1, Glitter: 1, Opalescent: 1, Speckle: 1,
  Modulex: 3, Rubber: 3, 'Transparent Rubber': 3, Fabric: 3,
  Obsolete: 4, 'Internal Common Material': 5,
};

/** Fold case, separators and the gray/grey split — the same normalization
 *  `brick_icons.colors.normalize_name` applies, so what the field offers is
 *  what `--part-color` will resolve. */
function fold(s: string): string {
  return s.trim().toLowerCase().replace(/[_\- ]/g, '').replace(/gray/g, 'grey');
}

/** LDConfig spells a family out; the list has room for a tag, not a phrase. */
const FAMILY_SHORT: Record<string, string> = {
  'Pearlescent Plastic': 'pearl', Pearlescent: 'pearl',
  'Metallic Paint': 'metallic', 'Chrome Plated': 'chrome',
  'Fluorescent Paint': 'fluorescent', 'Transparent Rubber': 'rubber trans',
  'Internal Common Material': 'internal',
};

/** What to tag a row with. Solid is what a reader assumes, so it gets no tag
 *  rather than 200 rows all saying the same word. */
export function familyLabel(category: string): string {
  if (!category || category === 'Solid') return '';
  return (FAMILY_SHORT[category] ?? category).toLowerCase();
}

/** Rank a family, then keep the palette's own order inside it. */
function byFamily(rows: readonly LdrawColor[]): LdrawColor[] {
  return rows
    .map((color, i) => ({ color, i }))
    .sort((a, b) => (FAMILY_RANK[a.color.category] ?? 2) - (FAMILY_RANK[b.color.category] ?? 2)
      || a.i - b.i)
    .map((x) => x.color);
}

/** Every palette entry worth offering for what has been typed so far. A code
 *  matches whole, a name matches anywhere inside it, and hex matches nothing:
 *  it already says what it means. Uncapped — the list scrolls, and which of
 *  322 colors is wanted is not something a cutoff can guess.
 *
 *  `expanded` opens the LDraw-only entries. Narrow, the list is the colors
 *  LDConfig gives a LEGO number to; an exact code is found either way, because
 *  `--part-color` takes any of them. */
export function matchColors(palette: readonly LdrawColor[], typed: string,
                            expanded = false): LdrawColor[] {
  const q = typed.trim();
  const offered = expanded ? palette : palette.filter((c) => c.legoId != null);
  if (!q) return byFamily(offered);
  if (HEX.test(q) && !/^\d{1,5}$/.test(q)) return [];
  const byCode = palette.filter((c) => String(c.code) === q);
  const folded = fold(q);
  const byName = offered.filter((c) => !byCode.includes(c) && fold(c.name).includes(folded));
  return [...byCode, ...byFamily(byName)];
}

/** What to paint the swatch. A transparent color drawn opaque reads as a
 *  different color, so its alpha rides along. */
export function swatchFor(color: LdrawColor): string {
  if (color.alpha >= 255) return color.hex;
  return `${color.hex}${color.alpha.toString(16).padStart(2, '0')}`;
}
