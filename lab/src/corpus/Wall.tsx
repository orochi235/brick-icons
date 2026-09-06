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
import type { Band, Rect } from '@lab/corpus/layout';
import { paintCommands, RETIRED_WASH, type Appearance, type CellBadge,
  type CellCaption, type PaintCommand } from '@lab/corpus/paint';
import { DEFAULT_PALETTE, readPalette, type CellState, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { panToReveal } from '@lab/corpus/reveal';
import type { TintMode } from '@lab/corpus/tint';
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
  /** Group headers the layout asked for. Absent for a dense grid. */
  bands?: Band[];
  /** What a cell's color says. Outside `status` the thumbnail gives way to
   *  the ramp. */
  tint?: TintMode;
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

// A sheet with its corner turned up: the sticker every catalog draws. Stroked
// rather than filled, so it reads as a mark on the field instead of a blob.
function drawSticker(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  const fold = r * 0.62;
  const x0 = cx - r, y0 = cy - r, x1 = cx + r, y1 = cy + r;
  ctx.save();
  ctx.lineWidth = Math.max(1, r * 0.16);
  ctx.lineJoin = 'round';
  ctx.strokeStyle = ctx.fillStyle;
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y0);
  ctx.lineTo(x1, y1 - fold);
  ctx.lineTo(x1 - fold, y1);
  ctx.lineTo(x0, y1);
  ctx.closePath();
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x1, y1 - fold);
  ctx.lineTo(x1 - fold, y1 - fold);
  ctx.lineTo(x1 - fold, y1);
  ctx.stroke();
  ctx.restore();
}

// A five-pointed star, point up, filled in the current style.
function drawStar(ctx: CanvasRenderingContext2D, cx: number, cy: number, r: number) {
  const inner = r * 0.42;
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const reach = i % 2 === 0 ? r : inner;
    const angle = -Math.PI / 2 + (i * Math.PI) / 5;
    const x = cx + Math.cos(angle) * reach;
    const y = cy + Math.sin(angle) * reach;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
}

// A filled disc in one corner, on the letterbox margin rather than the
// drawing, which is centered. Reversed out so it reads over ink and over the
// white ground alike.
function drawBadge(ctx: CanvasRenderingContext2D, badge: CellBadge,
                   cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const size = Math.max(9, Math.min(20, cmd.dw * 0.14));
  const radius = size * 0.72;
  const inset = radius + cornerPad(cmd.dw, size);
  const cx = badge.corner === 'br' ? cmd.dx + cmd.dw - inset : cmd.dx + inset;
  const cy = badge.corner === 'br' ? cmd.dy + cmd.dh - inset : cmd.dy + inset;
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = badge.field;
  ctx.fill();
  ctx.fillStyle = badge.ink;
  if (badge.mark === 'star') {
    drawStar(ctx, cx, cy, radius * 0.66);
  } else if (badge.text) {
    ctx.font = `600 ${size}px ui-monospace, monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // Optically centered rather than metrically: a monospace capital carries
    // more side bearing on its left and sits high in the em box.
    ctx.fillText(badge.text, cx + size * 0.05, cy + size * 0.08);
  }
  ctx.restore();
}

// A caption in one of the corners the badges leave free, set straight onto
// the cell: the drawing is centered and letterboxed, so its corners are empty.
function drawCaption(ctx: CanvasRenderingContext2D, caption: CellCaption,
                     cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const size = Math.max(10, Math.min(18, cmd.dw * 0.1));
  const right = caption.corner === 'tr';
  ctx.save();
  ctx.font = `${size}px ui-monospace, monospace`;
  ctx.textAlign = right ? 'right' : 'left';
  ctx.textBaseline = 'middle';
  const pad = cornerPad(cmd.dw, size);
  ctx.fillStyle = caption.ink;
  ctx.fillText(caption.text,
               right ? cmd.dx + cmd.dw - pad : cmd.dx + pad,
               right ? cmd.dy + pad + size * 0.5 : cmd.dy + cmd.dh - pad - size * 0.5);
  ctx.restore();
}

/** How far a corner mark sits off the cell's edge. A fraction of the cell
 *  rather than of the mark: both the badge and the caption stop scaling at
 *  their floor sizes, so at the small end of the zoom a margin measured off
 *  them crowds the corner. */
function cornerPad(cellPx: number, size: number): number {
  return Math.max(size * 0.35, cellPx * 0.06);
}

/** How much of its cell a round cell fills across, and how tall its letter
 *  stands when there is room for one. */
const CIRCLE_SCALE = 0.6;
const GLYPH_SCALE = 0.62;

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
    for (const caption of cmd.captions ?? []) drawCaption(ctx, caption, { ...cmd, dx, dy });
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
    for (const caption of cmd.captions ?? []) drawCaption(ctx, caption, { ...cmd, dx, dy });
    for (const badge of cmd.badges ?? []) drawBadge(ctx, badge, { ...cmd, dx, dy });
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'fill') {
    ctx.fillStyle = cmd.fill;
    if (cmd.mark === 'sticker') {
      drawSticker(ctx, dx + cmd.dw / 2, dy + cmd.dh / 2, cmd.dw * CIRCLE_SCALE / 2);
    } else if (cmd.glyph) {
      // The category's initial, sized to the cell: a block of S says sticker
      // at a glance, and no filled square competes with the drawings around it.
      ctx.save();
      ctx.font = `600 ${cmd.dh * GLYPH_SCALE}px ui-monospace, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(cmd.glyph, dx + cmd.dw / 2, dy + cmd.dh / 2 + cmd.dh * 0.03);
      ctx.restore();
    } else if (cmd.shape === 'circle') {
      // Well inside the cell: an out-of-scope part is not competing for
      // attention with the ones the project is actually drawing.
      ctx.beginPath();
      ctx.ellipse(dx + cmd.dw / 2, dy + cmd.dh / 2,
                  cmd.dw * CIRCLE_SCALE / 2, cmd.dh * CIRCLE_SCALE / 2, 0, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillRect(dx, dy, cmd.dw, cmd.dh);
    }
    strokeBorder(ctx, { ...cmd, dx, dy });
    for (const caption of cmd.captions ?? []) drawCaption(ctx, caption, { ...cmd, dx, dy });
    if (cmd.caret) strokeCaret(ctx, { ...cmd, dx, dy }, palette);
  } else if (cmd.kind === 'label') {
    ctx.save();
    ctx.fillStyle = cmd.depth === 0 ? palette.label.fill : palette.sublabel.fill;
    ctx.font = `${cmd.depth === 0 ? 700 : 600} ${cmd.size}px ui-sans-serif, system-ui, sans-serif`;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(cmd.depth === 0 ? `${cmd.text}  ${cmd.count.toLocaleString()}`
                                 : cmd.text, dx, dy);
    ctx.restore();
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
                       appearance, bands, tint }: WallProps) {
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
      appearance, bands, tint,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette);
    }
  }, [cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, caretIndex,
      appearance, bands, tint, width, height]);

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
      appearance, bands, tint,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette, offset);
    }
  }, [loupe.visible, loupe.aim, loupe.factor, loupeCapability.diameter,
      cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, caretIndex,
      appearance, bands, tint, width, height]);

  const hitTest = (e: { clientX: number; clientY: number;
                         currentTarget: HTMLCanvasElement }) => {
    const [sx, sy] = clientToCanvas(e.currentTarget, e.clientX, e.clientY);
    const visible = visibleRange(rects, cam, { width, height });
    const cmds = paintCommands({ cells, rects, visible, cam, manifest, palette });
    for (let i = cmds.length - 1; i >= 0; i--) {
      const c = cmds[i]!;
      if (c.kind === 'label') continue;
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
