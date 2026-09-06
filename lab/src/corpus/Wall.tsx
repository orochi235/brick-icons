import {
  useEffect, useMemo, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent,
} from 'react';
import {
  clientToCanvas, viewToTransform, worldToScreen, useDecayLoop, viewportDragPanAction, zoomAt,
  type InvocationCtx, type OngoingHandle, type View,
} from '@weasel-js/core';
import { LoupeBubble, resolveLoupe, useLoupe } from '@weasel-js/labkit/loupe';
import { adjacent, impliedCaret, type Direction } from '@lab/corpus/caret';
import type { Rect } from '@lab/corpus/layout';
import { paintCommands, RETIRED_WASH, THUMB_GROUND, type Appearance, type CellBadge,
  type PaintCommand } from '@lab/corpus/paint';
import { DEFAULT_PALETTE, readPalette, type CellState, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { panToReveal } from '@lab/corpus/reveal';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
import '@lab/corpus/Wall.css';

const ARROW_DIRECTION: Record<string, Direction> = {
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
};

export interface WallProps {
  cells: Cell[];
  rects: Rect[];
  cam: View;
  sheet: HTMLImageElement | null;
  manifest: SheetManifest | null;
  loose: Map<string, HTMLImageElement>;
  vector: Map<string, CanvasImageSource>;
  width: number;
  height: number;
  highlight: CellState | null;
  explicitCaret: number | null;
  onExplicitCaretChange: (index: number | null) => void;
  onPan: (next: View) => void;
  onPick: (cell: Cell, at: { x: number; y: number }) => void;
  /** A drag has passed the threshold and the wall is moving under whatever
   *  is anchored to it. */
  onDragStart?: () => void;
  onOpen: (cell: Cell) => void;
  /** A drag shorter than this is a click that wobbled, not a pan -- the same
   *  distinction `e.detail === 2` draws between a double click and two
   *  singles. Defaults to the params panel's own tuned value. */
  dragThresholdPx?: number;
  /** Border and dim tuning, live from the params panel. */
  appearance?: Appearance;
}

function ongoingInvoker(action: typeof viewportDragPanAction) {
  if (!action.invoker || action.invoker.timing !== 'ongoing') {
    throw new Error('viewport.dragPan: expected an ongoing invoker');
  }
  return action.invoker;
}

const NOOP_MODIFIERS = { alt: false, ctrl: false, meta: false, shift: false };

// A thumbnail is an opaque tile, so a defect's color is hidden behind it;
// A stroke straddles its path, so inset by half the width -- otherwise it
// overshoots the cell and eats into its neighbors. Drawn over a thumbnail as
// readily as over an empty cell: a part that fails in another slot draws
// perfectly well here, and the frame is the only thing that says so.
function strokeBorder(ctx: CanvasRenderingContext2D,
                      cmd: { dx: number; dy: number; dw: number; dh: number;
                             border: string | null; borderWidth: number;
                             slash?: boolean }) {
  if (!cmd.border || cmd.borderWidth <= 0) return;
  const inset = cmd.borderWidth / 2;
  ctx.save();
  ctx.strokeStyle = cmd.border;
  ctx.lineWidth = cmd.borderWidth;
  ctx.strokeRect(cmd.dx + inset, cmd.dy + inset,
                 cmd.dw - cmd.borderWidth, cmd.dh - cmd.borderWidth);
  if (cmd.slash) {
    ctx.beginPath();
    ctx.moveTo(cmd.dx + inset, cmd.dy + inset);
    ctx.lineTo(cmd.dx + cmd.dw - inset, cmd.dy + cmd.dh - inset);
    ctx.stroke();
  }
  ctx.restore();
}

// Dashed and drawn outside the cell, so it never collides with the inset
// defect ring when a cell carries both.
function strokeCaret(ctx: CanvasRenderingContext2D,
                     cmd: { dx: number; dy: number; dw: number; dh: number },
                     palette: Palette) {
  ctx.save();
  ctx.strokeStyle = palette.caret;
  ctx.lineWidth = 2;
  ctx.setLineDash([4, 2]);
  ctx.strokeRect(cmd.dx - 1, cmd.dy - 1, cmd.dw + 2, cmd.dh + 2);
  ctx.restore();
}

// A filled disc in one corner, on the letterbox margin rather than the
// drawing, which is centered. Reversed out so it reads over ink and over the
// white ground alike.
function drawBadge(ctx: CanvasRenderingContext2D, badge: CellBadge,
                   cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const size = Math.max(9, Math.min(20, cmd.dw * 0.14));
  const radius = size * 0.72;
  const inset = radius + size * 0.3;
  const cx = badge.corner === 'br' ? cmd.dx + cmd.dw - inset : cmd.dx + inset;
  const cy = badge.corner === 'br' ? cmd.dy + cmd.dh - inset : cmd.dy + inset;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = badge.field;
  ctx.fill();
  ctx.font = `600 ${size}px ui-monospace, monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = badge.ink;
  ctx.fillText(badge.text, cx, cy + size * 0.06);
  ctx.restore();
}

// The years, across the top of a cell big enough to read them on. Drawn on a
// pill of the cell's own ground so it never lands on the drawing's own ink.
function drawLabel(ctx: CanvasRenderingContext2D, text: string, ground: string,
                   cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const size = Math.max(10, Math.min(18, cmd.dw * 0.1));
  const cx = cmd.dx + cmd.dw / 2;
  const cy = cmd.dy + size * 0.9;
  ctx.save();
  ctx.font = `${size}px ui-monospace, monospace`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const wide = ctx.measureText(text).width + size * 0.8;
  ctx.fillStyle = ground;
  ctx.fillRect(cx - wide / 2, cmd.dy + size * 0.2, wide, size * 1.4);
  ctx.fillStyle = '#4a4a4f';
  ctx.fillText(text, cx, cy);
  ctx.restore();
}

// Flattens a retired cell toward the wash color: white goes gray, ink goes
// gray, and the whole thumbnail drops in contrast without a second bake.
function washCell(ctx: CanvasRenderingContext2D, wash: number,
                  cmd: { dx: number; dy: number; dw: number; dh: number }) {
  ctx.save();
  ctx.globalAlpha = (ctx.globalAlpha || 1) * wash;
  ctx.fillStyle = RETIRED_WASH;
  ctx.fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh);
  ctx.restore();
}

/** One paint command, drawn into `ctx` and shifted by `offset` -- the loupe
 *  reuses this to redraw the same commands into its own small canvas,
 *  recentred on the aimed point rather than at their outer screen position. */
function drawPaintCommand(ctx: CanvasRenderingContext2D, cmd: PaintCommand,
                          sheet: HTMLImageElement | null, palette: Palette,
                          offset: { x: number; y: number } = { x: 0, y: 0 }) {
  const dx = cmd.dx + offset.x;
  const dy = cmd.dy + offset.y;
  if (cmd.kind === 'sprite' && sheet) {
    ctx.save();
    ctx.globalAlpha = cmd.alpha ?? 1;
    ctx.drawImage(sheet, cmd.sx, cmd.sy, cmd.sw, cmd.sh, dx, dy, cmd.dw, cmd.dh);
    if (cmd.wash) washCell(ctx, cmd.wash, { ...cmd, dx, dy });
    strokeBorder(ctx, { ...cmd, dx, dy });
    // After the border, not before: the badge sits in the corner the frame
    // runs through, and it is the badge that has to stay readable.
    if (cmd.label) drawLabel(ctx, cmd.label, THUMB_GROUND, { ...cmd, dx, dy });
    for (const badge of cmd.badges ?? []) drawBadge(ctx, badge, { ...cmd, dx, dy });
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'image') {
    ctx.save();
    ctx.globalAlpha = cmd.alpha ?? 1;
    // Under the same alpha as the image, so a dimmed vector cell fades the
    // way a dimmed sprite does -- the bakes carry this ground in their pixels.
    ctx.fillStyle = cmd.ground;
    ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    // A translucent raster lets the frame sit under the drawing, on the
    // ground; a baked PNG is opaque, so its frame has to go on top or vanish.
    if (cmd.translucent) strokeBorder(ctx, { ...cmd, dx, dy });
    ctx.drawImage(cmd.image, dx, dy, cmd.dw, cmd.dh);
    if (cmd.wash) washCell(ctx, cmd.wash, { ...cmd, dx, dy });
    if (!cmd.translucent) strokeBorder(ctx, { ...cmd, dx, dy });
    // After the border, not before: the badge sits in the corner the frame
    // runs through, and it is the badge that has to stay readable.
    if (cmd.label) drawLabel(ctx, cmd.label, THUMB_GROUND, { ...cmd, dx, dy });
    for (const badge of cmd.badges ?? []) drawBadge(ctx, badge, { ...cmd, dx, dy });
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'fill') {
    ctx.fillStyle = cmd.fill;
    ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    strokeBorder(ctx, { ...cmd, dx, dy });
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  }
}

/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, loose, vector, width, height,
                       highlight, explicitCaret, onExplicitCaretChange,
                       onPan, onPick, onOpen, onDragStart,
                       dragThresholdPx = DEFAULT_PARAMS.dragThresholdPx,
                       appearance }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [dragging, setDragging] = useState(false);
  const decay = useDecayLoop();
  const [palette, setPalette] = useState<Palette>(DEFAULT_PALETTE);

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

  // The six state colors are canvas fills, so CSS can only reach them
  // through `getComputedStyle` -- read once on mount and again whenever the
  // theme's mode or name attribute changes anywhere above the canvas, or a
  // params-panel color row writes a `style`-attribute custom property onto
  // `.lk-root`. The `.lk-root` watch is its own observer, scoped to that one
  // node rather than the whole subtree -- the draw effect below sets the
  // canvas's own `style.width`/`height` every frame, and a subtree watch for
  // `style` would re-trigger this on that write too.
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const update = () => setPalette(readPalette(canvas));
    update();
    const themeObserver = new MutationObserver(update);
    themeObserver.observe(document.documentElement, {
      attributes: true, attributeFilter: ['data-wzl-mode', 'data-wzl-theme'], subtree: true,
    });
    const root = canvas.closest('.lk-root');
    const rootObserver = root ? new MutationObserver(update) : null;
    rootObserver?.observe(root!, { attributes: true, attributeFilter: ['style'] });
    return () => { themeObserver.disconnect(); rootObserver?.disconnect(); };
  }, []);

  const loupeCapability = useMemo(() => resolveLoupe(true), []);
  const loupe = useLoupe({ capability: loupeCapability, hostRef: ref, enabled: false });
  const lensRef = useRef<HTMLCanvasElement>(null);

  const visible = useMemo(
    () => visibleRange(rects, cam, { width, height }),
    [rects, cam, width, height]);
  // Recomputed every frame the camera moves, so the implied caret drifts to
  // whatever cell has the most on-screen area while dragging or zooming.
  const implied = useMemo(
    () => impliedCaret(rects, visible, cam, { width, height }),
    [rects, visible, cam, width, height]);
  const caretIndex = explicitCaret ?? implied;
  const caretCell = caretIndex != null ? cells[caretIndex] : undefined;

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
    for (const cmd of paintCommands({
      cells, rects, visible, cam, manifest, palette, loose, vector, highlight, caret: caretIndex,
      appearance,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette);
    }
  }, [cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, caretIndex,
      appearance, width, height]);

  // The lens shows a magnified crop of what is already on screen -- zooming
  // in about a fixed point never brings a cell into view that the outer
  // canvas didn't already have in its own visible set, so this redraws the
  // same commands rather than recomputing visibility for the lens' own tiny
  // viewport.
  useEffect(() => {
    const canvas = lensRef.current;
    if (!canvas || !loupe.visible) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const d = loupeCapability.diameter;
    canvas.width = d * dpr;
    canvas.height = d * dpr;
    canvas.style.width = `${d}px`;
    canvas.style.height = `${d}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, d, d);
    ctx.imageSmoothingEnabled = true;
    const magCam = zoomAt(cam, loupe.aim, loupe.factor);
    const offset = { x: d / 2 - loupe.aim.x, y: d / 2 - loupe.aim.y };
    for (const cmd of paintCommands({
      cells, rects, visible, cam: magCam, manifest, palette, loose, vector, highlight, caret: caretIndex,
      appearance,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette, offset);
    }
  }, [loupe.visible, loupe.aim, loupe.factor, loupeCapability.diameter,
      cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, caretIndex,
      appearance, width, height]);

  const hitTest = (e: { clientX: number; clientY: number;
                         currentTarget: HTMLCanvasElement }) => {
    const [sx, sy] = clientToCanvas(e.currentTarget, e.clientX, e.clientY);
    const visible = visibleRange(rects, cam, { width, height });
    const cmds = paintCommands({ cells, rects, visible, cam, manifest, palette });
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
      if (Math.hypot(dx, dy) < dragThresholdPx) return;
      draggedRef.current = true;
      setDragging(true);
      onDragStart?.();
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

  // The trio WCAG actually asks for -- role, name, keyboard operability --
  // rather than a focusable DOM node per cell, which 24,591 of them rules
  // out. Arrows move the caret and make it explicit; Enter opens the same
  // card a click does; Escape drops back to the implied one.
  const onKeyDown = (e: ReactKeyboardEvent<HTMLCanvasElement>) => {
    const direction = ARROW_DIRECTION[e.key];
    if (direction) {
      e.preventDefault();
      if (caretIndex == null) return;
      const next = adjacent(rects, caretIndex, direction);
      if (next == null) return;
      onExplicitCaretChange(next);
      const rect = rects[next];
      if (rect) onPan(panToReveal(rect, camRef.current, { width, height }));
      return;
    }
    if (e.key === 'Enter') {
      if (caretCell == null || caretIndex == null) return;
      const rect = rects[caretIndex];
      if (!rect) return;
      const [sx, sy] = worldToScreen(rect.x + rect.w / 2, rect.y + rect.h / 2,
                                     viewToTransform(camRef.current));
      onPick(caretCell, { x: sx, y: sy });
      return;
    }
    if (e.key === 'Escape') onExplicitCaretChange(null);
  };

  return (
    <>
      <canvas
        ref={ref}
        className={dragging ? 'corpus-canvas corpus-canvas-dragging' : 'corpus-canvas'}
        width={width}
        height={height}
        tabIndex={0}
        onKeyDown={onKeyDown}
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
      {loupe.visible && (
        <LoupeBubble aim={loupe.aim} diameter={loupeCapability.diameter}>
          <canvas ref={lensRef} className="lk-loupe__canvas" />
        </LoupeBubble>
      )}
      <div className="corpus-caret-announce" aria-live="polite">
        {caretCell ? caretCell.title : ''}
      </div>
    </>
  );
}
