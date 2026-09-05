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
  onPick: (cell: Cell) => void;
}

/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, width, height,
                       onPick }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
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

  return (
    <canvas
      ref={ref}
      className="corpus-canvas"
      width={width}
      height={height}
      onClick={(e) => {
        const box = e.currentTarget.getBoundingClientRect();
        const sx = e.clientX - box.left;
        const sy = e.clientY - box.top;
        const hit = visibleRange(rects, cam, { width, height }).find((i) => {
          const r = rects[i]!;
          const p = { x: (r.x - cam.x) * cam.scale, y: (r.y - cam.y) * cam.scale };
          return sx >= p.x && sx <= p.x + r.w * cam.scale
              && sy >= p.y && sy <= p.y + r.h * cam.scale;
        });
        if (hit !== undefined && cells[hit]) onPick(cells[hit]!);
      }}
    />
  );
}
