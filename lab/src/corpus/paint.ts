import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { Cell, SheetManifest } from '@lab/corpus/types';

export interface CellStyle {
  fill: string;
  /** null means the state gets no border at all -- the unknown field colour
   *  recedes rather than competing with everything drawn on top of it. */
  border: string | null;
  weight: 'thick' | 'thin' | null;
}

export const CELL_FILL: Record<
  'defect' | 'failed' | 'timeout' | 'defectElsewhere' | 'problemElsewhere' | 'unknown',
  CellStyle
> = {
  unknown: { fill: '#3a3a3f', border: null, weight: null },
  timeout: { fill: '#e8d5cc', border: '#8a4a32', weight: 'thick' },
  failed: { fill: '#f0d0d0', border: '#b02020', weight: 'thick' },
  defect: { fill: '#f5e3b8', border: '#c8860d', weight: 'thick' },
  problemElsewhere: { fill: '#e8d5cc', border: '#8a4a32', weight: 'thin' },
  defectElsewhere: { fill: '#f5e3b8', border: '#c8860d', weight: 'thin' },
};

/** What a cell's colour says about it, worst-here-first then worst-elsewhere. */
export function fillFor(cell: Cell): CellStyle {
  if (cell.open_defects > 0) return CELL_FILL.defect;
  if (cell.error === 'TimeoutError') return CELL_FILL.timeout;
  if (cell.error) return CELL_FILL.failed;
  if (cell.open_defects_elsewhere > 0) return CELL_FILL.defectElsewhere;
  if (cell.error_elsewhere) return CELL_FILL.problemElsewhere;
  return CELL_FILL.unknown;
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

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number; ring: boolean }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string; border: string | null; borderWidth: number }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: HTMLImageElement; ring: boolean };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: View;
  manifest: SheetManifest | null;
  loose?: Map<string, HTMLImageElement>;
}

/** What to draw this frame, as data.
 *
 *  Kept separate from the canvas so the decisions -- which cells, from where,
 *  in what colour -- are testable without a rendering context, and so the
 *  drawing itself is the only thing weasel's mega view has to replace. */
export function paintCommands({ cells, rects, visible, cam, manifest, loose }:
                              PaintInput): PaintCommand[] {
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
    const image = loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image, ring });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    if (box) {
      out.push({ kind: 'sprite', dx, dy, dw, dh, ...box, ring });
      continue;
    }
    const style = fillFor(cell);
    out.push({ kind: 'fill', dx, dy, dw, dh, fill: style.fill,
               border: style.border, borderWidth: borderWidthFor(style.weight, dw) });
  }
  return out;
}
