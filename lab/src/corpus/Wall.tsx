import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import {
  clientToCanvas, useDecayLoop, viewportDragPanAction,
  type InvocationCtx, type OngoingHandle, type View,
} from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';
import { CELL_FILL, paintCommands } from '@lab/corpus/paint';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
import '@lab/corpus/Wall.css';

export interface WallProps {
  cells: Cell[];
  rects: Rect[];
  cam: View;
  sheet: HTMLImageElement | null;
  manifest: SheetManifest | null;
  loose: Map<string, HTMLImageElement>;
  width: number;
  height: number;
  onPan: (next: View) => void;
  onPick: (cell: Cell, at: { x: number; y: number }) => void;
  onOpen: (cell: Cell) => void;
}

// A drag shorter than this is a click that wobbled, not a pan -- the same
// distinction `e.detail === 2` draws between a double click and two singles.
const DRAG_THRESHOLD_PX = 4;

function ongoingInvoker(action: typeof viewportDragPanAction) {
  if (!action.invoker || action.invoker.timing !== 'ongoing') {
    throw new Error('viewport.dragPan: expected an ongoing invoker');
  }
  return action.invoker;
}

const NOOP_MODIFIERS = { alt: false, ctrl: false, meta: false, shift: false };

// A thumbnail is an opaque tile, so a defect's colour is hidden behind it;
// the ring is what makes a drawn cell's open defect findable.
function strokeRing(ctx: CanvasRenderingContext2D,
                     cmd: { dx: number; dy: number; dw: number; dh: number }) {
  ctx.save();
  ctx.strokeStyle = CELL_FILL.defect.border ?? CELL_FILL.defect.fill;
  ctx.lineWidth = 2;
  ctx.strokeRect(cmd.dx + 1, cmd.dy + 1, cmd.dw - 2, cmd.dh - 2);
  ctx.restore();
}

/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, loose, width, height,
                       onPan, onPick, onOpen }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [dragging, setDragging] = useState(false);
  const decay = useDecayLoop();

  // Read by the drag gesture, which spans several pointer events and must see
  // the live camera -- not the value closed over at the pointerdown that
  // started it.
  const camRef = useRef(cam);
  camRef.current = cam;
  const handleRef = useRef<OngoingHandle | null>(null);
  const draggedRef = useRef(false);
  const suppressClickRef = useRef(false);
  const startRef = useRef({ x: 0, y: 0 });

  const view = { get: () => camRef.current, set: onPan, decay: decay.start };

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
    for (const cmd of paintCommands({ cells, rects, visible, cam, manifest, loose })) {
      if (cmd.kind === 'sprite' && sheet) {
        ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh,
                      cmd.dx, cmd.dy, cmd.dw, cmd.dh);
        if (cmd.ring) strokeRing(ctx, cmd);
      } else if (cmd.kind === 'image') {
        ctx.drawImage(cmd.image, cmd.dx, cmd.dy, cmd.dw, cmd.dh);
        if (cmd.ring) strokeRing(ctx, cmd);
      } else if (cmd.kind === 'fill') {
        ctx.fillStyle = cmd.fill;
        ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
        if (cmd.border) {
          // A stroke straddles its path, so inset by half the width --
          // otherwise it overshoots the cell and eats into its neighbours.
          const inset = cmd.borderWidth / 2;
          ctx.save();
          ctx.strokeStyle = cmd.border;
          ctx.lineWidth = cmd.borderWidth;
          ctx.strokeRect(cmd.dx + inset, cmd.dy + inset,
                         cmd.dw - cmd.borderWidth, cmd.dh - cmd.borderWidth);
          ctx.restore();
        }
      }
    }
  }, [cells, rects, cam, sheet, manifest, loose, width, height]);

  const hitTest = (e: { clientX: number; clientY: number;
                         currentTarget: HTMLCanvasElement }) => {
    const [sx, sy] = clientToCanvas(e.currentTarget, e.clientX, e.clientY);
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

  const dragCtx = (screenDelta: { x: number; y: number }): InvocationCtx => ({
    world: { x: 0, y: 0 }, screen: { x: 0, y: 0 }, modifiers: NOOP_MODIFIERS,
    deps: { view },
    drag: { start: { x: 0, y: 0 }, current: screenDelta, delta: screenDelta,
            screenDelta },
  });

  // A plain onPointerDown/Move/Up trio with pointer capture, rather than
  // weasel's `openPointerSession`: that helper (lost-capture and missed-release
  // recovery included) landed in core after 1.4.0, the version this lab has.
  const onPointerDown = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    // Best-effort: capture keeps the drag alive once the pointer leaves the
    // canvas, but its absence is not a reason to refuse the drag.
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* uncaptured is fine */ }
    startRef.current = { x: e.clientX, y: e.clientY };
    draggedRef.current = false;
    handleRef.current = ongoingInvoker(viewportDragPanAction)
      .start(dragCtx({ x: 0, y: 0 }), { params: { inertia: {} } });
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!handleRef.current) return;
    const dx = e.clientX - startRef.current.x;
    const dy = e.clientY - startRef.current.y;
    if (!draggedRef.current) {
      if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
      draggedRef.current = true;
      setDragging(true);
    }
    handleRef.current.onMove?.(dragCtx({ x: dx, y: dy }));
  };

  const endDrag = (e: ReactPointerEvent<HTMLCanvasElement>,
                    reason: 'commit' | 'cancel') => {
    if (!handleRef.current) return;
    const dx = e.clientX - startRef.current.x;
    const dy = e.clientY - startRef.current.y;
    handleRef.current.onEnd?.(dragCtx({ x: dx, y: dy }), reason);
    handleRef.current = null;
    setDragging(false);
    if (reason === 'commit' && draggedRef.current) suppressClickRef.current = true;
  };

  return (
    <canvas
      ref={ref}
      className={dragging ? 'corpus-canvas corpus-canvas-dragging' : 'corpus-canvas'}
      width={width}
      height={height}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={(e) => endDrag(e, 'commit')}
      onPointerCancel={(e) => endDrag(e, 'cancel')}
      onClick={(e) => {
        if (suppressClickRef.current) { suppressClickRef.current = false; return; }
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
