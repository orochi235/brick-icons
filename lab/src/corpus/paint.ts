import type { Camera } from '@lab/corpus/camera';
import { toScreen } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';
import { isStale, sourceBox } from '@lab/corpus/sheet';
import type { Cell, SheetManifest } from '@lab/corpus/types';

export const STATUS_FILL: Record<string, string> = {
  unreviewed: '#2a2a2e',
  good: '#1f3a24',
  suspect: '#4a3a12',
  broken: '#4a1c1c',
  wontfix: '#232326',
};

export type PaintCommand =
  | { kind: 'sprite'; dx: number; dy: number; dw: number; dh: number;
      sx: number; sy: number; sw: number; sh: number }
  | { kind: 'fill'; dx: number; dy: number; dw: number; dh: number;
      fill: string }
  | { kind: 'image'; dx: number; dy: number; dw: number; dh: number;
      image: HTMLImageElement };

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
    const image = loose?.get(cell.id);
    if (image) {
      out.push({ kind: 'image', dx, dy, dw, dh, image });
      continue;
    }
    const box = manifest && cell.sha && !isStale(manifest, cell)
      ? sourceBox(manifest, cell.index)
      : null;
    out.push(box
      ? { kind: 'sprite', dx, dy, dw, dh, ...box }
      : { kind: 'fill', dx, dy, dw, dh,
          fill: STATUS_FILL[cell.status] ?? STATUS_FILL.unreviewed! });
  }
  return out;
}
