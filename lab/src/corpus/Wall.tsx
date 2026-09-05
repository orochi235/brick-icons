import { useEffect, useRef } from 'react';
import type { Camera } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';
import { paintCommands } from '@lab/corpus/paint';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
import '@lab/corpus/Wall.css';

export interface WallProps {
  cells: Cell[];
  rects: Rect[];
  cam: Camera;
  sheet: HTMLImageElement | null;
  manifest: SheetManifest | null;
  width: number;
  height: number;
  onPick: (cell: Cell, at: { x: number; y: number }) => void;
  onOpen: (cell: Cell) => void;
}

/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, width, height,
                       onPick, onOpen }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    // The backing store is oversized for sharpness; without pinning the CSS
    // size back down the canvas displays at the backing-store size and
    // overflows its container on any dpr != 1.
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = true;
    const visible = visibleRange(rects, cam, { width, height });
    for (const cmd of paintCommands({ cells, rects, visible, cam, manifest })) {
      if (cmd.kind === 'sprite' && sheet) {
        ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh,
                      cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      } else if (cmd.kind === 'fill') {
        ctx.fillStyle = cmd.fill;
        ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
      }
    }
  }, [cells, rects, cam, sheet, manifest, width, height]);

  const hitTest = (e: { clientX: number; clientY: number;
                         currentTarget: HTMLCanvasElement }) => {
    const box = e.currentTarget.getBoundingClientRect();
    const sx = e.clientX - box.left;
    const sy = e.clientY - box.top;
    const visible = visibleRange(rects, cam, { width, height });
    const cmds = paintCommands({ cells, rects, visible, cam, manifest });
    for (let i = cmds.length - 1; i >= 0; i--) {
      const c = cmds[i]!;
      if (sx >= c.dx && sx <= c.dx + c.dw && sy >= c.dy && sy <= c.dy + c.dh) {
        const cell = cells[visible[i]!];
        if (cell) return { cell, at: { x: sx, y: sy } };
        return null;
      }
    }
    return null;
  };

  return (
    <canvas
      ref={ref}
      className="corpus-canvas"
      width={width}
      height={height}
      onClick={(e) => {
        // A double click's first click also fires this handler; e.detail
        // marks it so onDoubleClick handles it instead and the card never
        // flashes before the lightbox opens.
        if (e.detail === 2) return;
        const hit = hitTest(e);
        if (hit) onPick(hit.cell, hit.at);
      }}
      onDoubleClick={(e) => {
        const hit = hitTest(e);
        if (hit) onOpen(hit.cell);
      }}
    />
  );
}
