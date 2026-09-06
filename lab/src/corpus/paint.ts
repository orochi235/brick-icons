import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';
import { CELL_STATES, type CellState, type CellStyle, type Palette } from '@lab/corpus/palette';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { Cell, SheetManifest } from '@lab/corpus/types';

export type { CellStyle } from '@lab/corpus/palette';

/** What a cell's color says about it, worst-here-first then worst-elsewhere.
 *  The single precedence table -- `fillFor`, the legend and `PartCard` all
 *  read a cell's state through this, so they cannot drift apart. */
export function cellState(cell: Cell): CellState {
  if (cell.open_defects > 0) return 'defect';
  if (cell.error === 'TimeoutError') return 'timeout';
  if (cell.error) return 'failed';
  if (cell.open_defects_elsewhere > 0) return 'defectElsewhere';
  if (cell.error_elsewhere) return 'problemElsewhere';
  return 'unknown';
}

export function fillFor(cell: Cell, palette: Palette): CellStyle {
  return palette[cellState(cell)];
}

/** How many cells are in each state -- a pure count over cells already in
 *  hand, so the legend can show a summary of the corpus without a request. */
export function tally(cells: Cell[]): Record<CellState, number> {
  const out = Object.fromEntries(CELL_STATES.map((s) => [s, 0])) as Record<CellState, number>;
  for (const cell of cells) out[cellState(cell)] += 1;
  return out;
}

// A fixed pixel width vanishes when the wall is zoomed out, which is the case
// that matters most -- so the border scales with the drawn cell, capped
// before it turns a large cell into a picture frame.
const THICK_BORDER_FACTOR = 0.18;
const THIN_BORDER_FACTOR = 0.09;
const MAX_BORDER_PX = 6;

function borderWidthFor(weight: CellStyle['weight'], cellPx: number): number {
  if (!weight) return 0;
  const factor = weight === 'thick' ? THICK_BORDER_FACTOR : THIN_BORDER_FACTOR;
  return Math.min(MAX_BORDER_PX, Math.max(1, cellPx * factor));
}

// A cell not in the highlighted state recedes into the same flat tone as the
// unknown field, rather than a scaled-down version of its own color -- on a
// wall this dense a tinted dim reads as noise, while matching the field
// exactly makes only the highlighted state's cells read as distinct.
const DIM_ALPHA = 0.25;

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number; ring: boolean; alpha?: number;
      caret?: boolean }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string; border: string | null; borderWidth: number; caret?: boolean }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: HTMLImageElement; ring: boolean; alpha?: number; caret?: boolean };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: View;
  manifest: SheetManifest | null;
  palette: Palette;
  loose?: Map<string, HTMLImageElement>;
  /** The legend's hovered or focused row, if any -- cells outside this state
   *  are painted dimmed rather than the matching cells being brightened. */
  highlight?: CellState | null;
  /** Index of the caret cell, if any -- explicit or implied, resolved by the
   *  caller (`caret.ts`). */
  caret?: number | null;
}

/** What to draw this frame, as data.
 *
 *  Kept separate from the canvas so the decisions -- which cells, from where,
 *  in what color -- are testable without a rendering context, and so the
 *  drawing itself is the only thing weasel's mega view has to replace. */
export function paintCommands({ cells, rects, visible, cam, manifest, palette, loose,
                                highlight = null, caret = null }: PaintInput): PaintCommand[] {
  const out: PaintCommand[] = [];
  const transform = viewToTransform(cam);
  for (const i of visible) {
    const cell = cells[i];
    const rect = rects[i];
    if (!cell || !rect) continue;
    const [dx, dy] = worldToScreen(rect.x, rect.y, transform);
    const dw = rect.w * cam.scale.x;
    const dh = rect.h * cam.scale.y;
    const ring = cell.open_defects > 0;
    const isCaret = caret != null && i === caret ? true : undefined;
    const state = cellState(cell);
    const dimmed = highlight !== null && highlight !== state;
    const alpha = dimmed ? DIM_ALPHA : undefined;
    const image = loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image, ring, alpha, caret: isCaret });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    if (box) {
      out.push({ kind: 'sprite', dx, dy, dw, dh, ...box, ring, alpha, caret: isCaret });
      continue;
    }
    const style = dimmed ? palette.unknown : palette[state];
    out.push({ kind: 'fill', dx, dy, dw, dh, fill: style.fill,
               border: style.border, borderWidth: borderWidthFor(style.weight, dw),
               caret: isCaret });
  }
  return out;
}
