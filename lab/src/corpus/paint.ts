import type { Camera } from '@lab/corpus/camera';
import { toScreen } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { Cell, SheetManifest } from '@lab/corpus/types';

export const CELL_FILL = {
  defect: '#c8860d',
  failed: '#8c2020',
  timeout: '#5a3326',
  defectElsewhere: '#6b5220',
  problemElsewhere: '#4a2a2a',
  unknown: '#3a3a3f',
} as const;

/** What a cell's colour says about it, worst-here-first then worst-elsewhere. */
export function fillFor(cell: Cell): string {
  if (cell.open_defects > 0) return CELL_FILL.defect;
  if (cell.error === 'TimeoutError') return CELL_FILL.timeout;
  if (cell.error) return CELL_FILL.failed;
  if (cell.open_defects_elsewhere > 0) return CELL_FILL.defectElsewhere;
  if (cell.error_elsewhere) return CELL_FILL.problemElsewhere;
  return CELL_FILL.unknown;
}

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number; ring: boolean }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: HTMLImageElement; ring: boolean };

export interface PaintInput {
  cells: Cell[];
  rects: Rect[];
  visible: number[];
  cam: Camera;
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
  for (const i of visible) {
    const cell = cells[i];
    const rect = rects[i];
    if (!cell || !rect) continue;
    const { x: dx, y: dy } = toScreen(cam, rect.x, rect.y);
    const dw = rect.w * cam.scale;
    const dh = rect.h * cam.scale;
    const ring = cell.open_defects > 0;
    const image = loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image, ring });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    out.push(box
      ? { kind: 'sprite', dx, dy, dw, dh, ...box, ring }
      : { kind: 'fill', dx, dy, dw, dh, fill: fillFor(cell) });
  }
  return out;
}
