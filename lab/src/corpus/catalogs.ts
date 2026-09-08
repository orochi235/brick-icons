/** Where a part id can be looked up outside this project.
 *
 *  LDraw's own library goes through its search page on purpose:
 *  `library.ldraw.org/parts/3001` is a row id, not a part number, and serves
 *  a different part entirely (2708.dat).
 */
export interface Catalog {
  name: string;
  url: (partId: string) => string;
}

export const CATALOGS: Catalog[] = [
  { name: 'Rebrickable',
    url: (id) => `https://rebrickable.com/parts/${encodeURIComponent(id)}/` },
  { name: 'BrickLink',
    url: (id) => 'https://www.bricklink.com/v2/catalog/catalogitem.page?P='
                 + encodeURIComponent(id) },
  { name: 'Brickset',
    url: (id) => `https://brickset.com/parts/design-${encodeURIComponent(id)}` },
  { name: 'LDraw library',
    url: (id) => `https://library.ldraw.org/search?q=${encodeURIComponent(id)}` },
];
