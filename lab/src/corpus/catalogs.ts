/** Where a part id can be looked up outside this project.
 *
 *  LDraw's own library goes through its search page on purpose:
 *  `library.ldraw.org/parts/3001` is a row id, not a part number, and serves
 *  a different part entirely (2708.dat).
 */
export interface Catalog {
  name: string;
  url: (partId: string) => string;
  /** The id the catalog is asked for, when it is not the LDraw id itself. */
  key?: (partId: string) => string;
}

/** The LEGO design number an LDraw id starts with. BrickLink keys its
 *  catalog on it since dropping the mould letter (3068b is its 3068, and
 *  P=3068b is "Page Not Found"), Brickset only ever did, and neither knows
 *  LDraw's print or sticker suffix: 3840d01 is a dead page on both, 3840 is
 *  the vest. An LDraw-assigned `u…` id has no number and goes as it is. */
export function designNumber(id: string): string {
  const m = /^\d+/.exec(id);
  return m ? m[0] : id;
}

export const CATALOGS: Catalog[] = [
  { name: 'Rebrickable',
    url: (id) => `https://rebrickable.com/parts/${encodeURIComponent(id)}/` },
  { name: 'BrickLink', key: designNumber,
    url: (id) => 'https://www.bricklink.com/v2/catalog/catalogitem.page?P='
                 + encodeURIComponent(designNumber(id)) },
  { name: 'Brickset', key: designNumber,
    url: (id) => `https://brickset.com/parts/design-${encodeURIComponent(designNumber(id))}` },
  { name: 'LDraw library',
    url: (id) => `https://library.ldraw.org/search?q=${encodeURIComponent(id)}` },
];
