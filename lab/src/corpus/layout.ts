import type { Cell } from '@lab/corpus/types';

export interface Rect { x: number; y: number; w: number; h: number }

export interface LayoutOptions {
  /** Edge of one cell in world units. */
  cell: number;
  /** Space between cells in world units. */
  gap: number;
  cols: number;
}

/** A layout answers where each cell sits, and nothing else. It never touches
 *  the atlas, so re-sorting or regrouping the wall rebakes nothing. */
export type Layout = (cells: Cell[], opts: LayoutOptions) =>
  { rects: Rect[]; bounds: { w: number; h: number } };

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
    bounds: cells.length
      ? { w: Math.min(cells.length, cols) * pitch - gap, h: rows * pitch - gap }
      : { w: 0, h: 0 },
  };
};
