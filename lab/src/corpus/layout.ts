import type { Cell } from '@lab/corpus/types';

export interface Rect { x: number; y: number; w: number; h: number }

export interface LayoutOptions {
  /** Edge of one cell in world units. */
  cell: number;
  /** Space between cells in world units. */
  gap: number;
  cols: number;
}

/** A group header a layout wants drawn. `depth` 0 is the outer band, 1 an
 *  inner block inside it -- so paint styles the two without a second field,
 *  and a third level costs the type nothing. */
export interface Band {
  key: string;
  label: string;
  count: number;
  rect: Rect;
  depth: 0 | 1;
}

/** A layout answers where each cell sits, and nothing else. It never touches
 *  the atlas, so re-sorting or regrouping the wall rebakes nothing. */
export type Layout = (cells: Cell[], opts: LayoutOptions) =>
  { rects: Rect[]; bands: Band[]; bounds: { w: number; h: number } };

export const gridLayout: Layout = (cells, { cell, gap, cols }) => {
  const pitch = cell + gap;
  const rects = cells.map((_, i) => ({
    x: (i % cols) * pitch,
    y: Math.floor(i / cols) * pitch,
    w: cell,
    h: cell,
  }));
  const rows = Math.ceil(cells.length / cols);
  return {
    rects,
    bands: [],
    bounds: cells.length
      ? { w: Math.min(cells.length, cols) * pitch - gap, h: rows * pitch - gap }
      : { w: 0, h: 0 },
  };
};
