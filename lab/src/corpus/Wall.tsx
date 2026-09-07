import {
  useEffect, useMemo, useRef, useState,
  type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent,
} from 'react';
import {
  clientToCanvas, viewToTransform, worldToScreen, useDecayLoop, usePinchGesture,
  viewportDragPanAction, zoomAt,
  type InvocationCtx, type OngoingHandle, type View,
} from '@weasel-js/core';
import { LoupeBubble, resolveLoupe, useLoupe } from '@weasel-js/labkit/loupe';
import { adjacent, impliedCaret, type Direction } from '@lab/corpus/caret';
import type { Band, Rect } from '@lab/corpus/layout';
import { BADGE_FACE, BADGE_WEIGHT, THUMB_FACE, WEIGHT_ID, WEIGHT_TEXT,
         drawBadge } from '@lab/corpus/badges';
import { badgeGeometry, captionSize, cornerPad, LINKED_BADGE, paintCommands,
  RETIRED_WASH, stripGeometry, type Appearance, type CellBadge, type CellCaption,
  type PaintCommand } from '@lab/corpus/paint';
import { DEFAULT_PALETTE, readPalette, type CellState, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { pinchStep } from '@lab/corpus/pinch';
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
  /** The legend's hovered tag row, if any -- cells without it paint dimmed. */
  highlightTag: string | null;
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

// A filled disc in one corner, on the letterbox margin rather than the
// drawing, which is centered. Reversed out so it reads over ink and over the
// white ground alike.
/** Where a corner badge's disc sits. Shared with the hit test, so a click
 *  cannot land somewhere the disc is not drawn. */
export function cornerBadgeAt(badge: CellBadge,
                              cmd: { dx: number; dy: number; dw: number; dh: number }) {
  const { size, radius, inset } = badgeGeometry(cmd.dw);
  const right = badge.corner === 'br' || badge.corner === 'tr';
  const bottom = badge.corner === 'br';
  return {
    cx: right ? cmd.dx + cmd.dw - inset : cmd.dx + inset,
    cy: bottom ? cmd.dy + cmd.dh - inset : cmd.dy + inset,
    size, radius,
  };
}

/** The kind badges, running right along the bottom edge from wherever the
 *  part number ended. Stops short of the bottom-right corner rather than
 *  drawing under the badge that lives there. */
/** Half a capital's height in the current font, measured rather than
 *  assumed: it is what turns the caption's `middle` position into the
 *  baseline the badges have to sit on. */
function capHalf(ctx: CanvasRenderingContext2D, size: number): number {
  const ascent = ctx.measureText('H').actualBoundingBoxAscent;
  return Number.isFinite(ascent) && ascent > 0 ? ascent / 2 : size * 0.35;
}

function drawStrip(ctx: CanvasRenderingContext2D, strip: CellBadge[],
                   cmd: { dx: number; dy: number; dw: number; dh: number },
                   startX: number) {
  if (strip.length === 0) return;
  const { size, radius } = stripGeometry(cmd.dw);
  const gap = radius * 0.5;
  // Stop at the corner badge's left edge, not a badge-width short of it:
  // `inset` is already that badge's center, so subtracting a strip diameter
  // on top of it cost the strip about two badges' room.
  const corner = badgeGeometry(cmd.dw);
  const limit = cmd.dx + cmd.dw - corner.inset - corner.radius - gap;
  ctx.save();
  ctx.font = `${BADGE_WEIGHT} ${size}px ${BADGE_FACE}`;
  const half = capHalf(ctx, size);
  ctx.restore();
  // The part number's baseline, derived from where drawCaption centers it.
  const baseline = cmd.dy + cmd.dh - cornerPad(cmd.dw, size) - size * 0.5 + half;
  const cy = baseline - half;
  let cx = startX + radius;
  for (const badge of strip) {
    if (cx + radius > limit) return;
    drawBadge(ctx, badge, { cx, cy, size, radius, baseline });
    cx += radius * 2 + gap;
  }
}

// A caption in one of the corners the badges leave free, set straight onto
// the cell: the drawing is centered and letterboxed, so its corners are empty.
function drawCaption(ctx: CanvasRenderingContext2D, caption: CellCaption,
                     cmd: { dx: number; dy: number; dw: number; dh: number },
                     rightPad = 0): number {
  const size = captionSize(cmd.dw);
  const right = caption.corner === 'tr';
  const top = caption.corner[0] === 't';
  ctx.save();
  ctx.font = `${caption.weight ?? WEIGHT_TEXT} ${size}px ${THUMB_FACE}`;
  ctx.textAlign = right ? 'right' : 'left';
  ctx.textBaseline = 'middle';
  const pad = cornerPad(cmd.dw, size);
  ctx.fillStyle = caption.ink;
  const x = right ? cmd.dx + cmd.dw - pad - rightPad : cmd.dx + pad;
  ctx.fillText(caption.text, x,
               top ? cmd.dy + pad + size * 0.5 : cmd.dy + cmd.dh - pad - size * 0.5);
  const width = ctx.measureText(caption.text).width;
  ctx.restore();
  return right ? x - width : x + width;
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

/** The captions, corner discs and kind strip a drawn cell wears. The strip
 *  starts where the part number ended, so it has to run after the captions. */
function drawOverlays(ctx: CanvasRenderingContext2D,
                      cmd: { captions?: CellCaption[]; badges?: CellBadge[];
                             strip?: CellBadge[] },
                      box: { dx: number; dy: number; dw: number; dh: number }) {
  const { size, radius } = stripGeometry(box.dw);
  let stripX = box.dx + cornerPad(box.dw, size);
  // The top-right discs are drawn at the corner, so the year has to set to
  // their left or the two overlap. Measured off the same geometry the discs
  // are placed with, never a guess at how many there are.
  const topRight = (cmd.badges ?? []).filter((b) => b.corner === 'tr').length;
  const trPad = topRight === 0 ? 0
    : topRight * badgeGeometry(box.dw).radius * 2 + radius * 0.6;
  for (const caption of cmd.captions ?? []) {
    const end = drawCaption(ctx, caption, box, caption.corner === 'tr' ? trPad : 0);
    if (caption.corner === 'bl') stripX = end + radius * 0.6;
  }
  for (const badge of cmd.badges ?? []) drawBadge(ctx, badge, cornerBadgeAt(badge, box));
  drawStrip(ctx, cmd.strip ?? [], box, stripX);
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
    drawOverlays(ctx, cmd, { ...cmd, dx, dy });
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
    drawOverlays(ctx, cmd, { ...cmd, dx, dy });
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
      ctx.font = `${WEIGHT_ID} ${cmd.dh * GLYPH_SCALE}px ${THUMB_FACE}`;
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
                       highlight, highlightTag, explicitCaret, onExplicitCaretChange,
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
  // Which pointers are on the glass, and which one the pan is following --
  // a touch canvas gets more than one, and only the first of them pans.
  const downRef = useRef(new Set<number>());
  const dragPointerRef = useRef<number | null>(null);
  const pinchAtRef = useRef<{ x: number; y: number } | null>(null);

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
  const byId = useMemo(() => new Map(cells.map((c, i) => [c.id, i])), [cells]);

  /** Follow an updated badge to the part that replaced this one: put the
   *  caret on it and bring it on screen, the same move an arrow key makes. */
  const goToSuccessor = (cell: Cell): boolean => {
    if (!cell.successor) return false;
    const next = byId.get(cell.successor);
    if (next == null) return false;
    onExplicitCaretChange(next);
    const rect = rects[next];
    if (rect) onPan(panToReveal(rect, camRef.current, { width, height }));
    return true;
  };

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
      cells, rects, visible, cam, manifest, palette, loose, vector, highlight, highlightTag,
      caret: caretIndex,
      appearance, bands, tint,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette);
    }
  }, [cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, highlightTag,
      caretIndex,
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
      cells, rects, visible, cam: magCam, manifest, palette, loose, vector, highlight, highlightTag,
      caret: caretIndex,
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
        if (!cell) return null;
        // Before the cell itself: the updated badge goes somewhere else, and
        // it sits inside the cell's own box.
        const badge = (('badges' in c ? c.badges : undefined) ?? []).find((b) => {
          if (b.tag !== LINKED_BADGE) return false;
          const { cx, cy, radius } = cornerBadgeAt(b, c);
          return Math.hypot(sx - cx, sy - cy) <= radius;
        });
        return { cell, at: { x: sx, y: sy }, badge };
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

  const endDrag = (delta: { x: number; y: number }, reason: 'commit' | 'cancel') => {
    dragPointerRef.current = null;
    if (!handleRef.current) return;
    handleRef.current.onEnd?.(dragCtx(delta), reason);
    handleRef.current = null;
    setDragging(false);
    if (reason === 'commit' && draggedRef.current) suppressClickRef.current = true;
  };

  const dragDelta = (e: ReactPointerEvent<HTMLCanvasElement>) =>
    ({ x: e.clientX - startRef.current.x, y: e.clientY - startRef.current.y });

  // A plain onPointerDown/Move/Up trio with pointer capture, rather than
  // weasel's `openPointerSession`: that helper (lost-capture and missed-release
  // recovery included) landed in core after 1.4.0, the version this lab has.
  const onPointerDown = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    downRef.current.add(e.pointerId);
    // A second finger turns the gesture into a pinch, which `usePinchGesture`
    // drives -- and a one-finger pan that carried on underneath it would
    // fight the zoom for the same camera.
    if (downRef.current.size > 1) { endDrag({ x: 0, y: 0 }, 'cancel'); return; }
    if (e.button !== 0) return;
    // Not every gesture ends in a click that would clear it -- a pinch
    // usually ends in none at all -- so a fresh press is what unlatches it.
    suppressClickRef.current = false;
    // Best-effort: capture keeps the drag alive once the pointer leaves the
    // canvas, but its absence is not a reason to refuse the drag.
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* uncaptured is fine */ }
    startRef.current = { x: e.clientX, y: e.clientY };
    draggedRef.current = false;
    dragPointerRef.current = e.pointerId;
    handleRef.current = ongoingInvoker(viewportDragPanAction)
      .start(dragCtx({ x: 0, y: 0 }), { params: { inertia: {} } });
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!handleRef.current || e.pointerId !== dragPointerRef.current) return;
    const { x: dx, y: dy } = dragDelta(e);
    if (!draggedRef.current) {
      if (Math.hypot(dx, dy) < dragThresholdPx) return;
      draggedRef.current = true;
      setDragging(true);
      onDragStart?.();
    }
    handleRef.current.onMove?.(dragCtx({ x: dx, y: dy }));
  };

  const onPointerRelease = (e: ReactPointerEvent<HTMLCanvasElement>,
                            reason: 'commit' | 'cancel') => {
    downRef.current.delete(e.pointerId);
    if (downRef.current.size < 2) pinchAtRef.current = null;
    if (e.pointerId === dragPointerRef.current) endDrag(dragDelta(e), reason);
  };

  // Two-finger zoom, anchored where the fingers are so the cell under them
  // stays under them. The midpoint travels too, which is the same gesture's
  // pan -- see `pinchStep`.
  usePinchGesture(ref, (clientAnchor, factor) => {
    const canvas = ref.current;
    if (!canvas) return;
    const [x, y] = clientToCanvas(canvas, clientAnchor.x, clientAnchor.y);
    // Whatever was anchored to a cell is about to be somewhere else.
    if (!pinchAtRef.current) onDragStart?.();
    onPan(pinchStep(camRef.current, { x, y }, pinchAtRef.current, factor));
    pinchAtRef.current = { x, y };
    suppressClickRef.current = true;
  });

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
        onPointerUp={(e) => onPointerRelease(e, 'commit')}
        onPointerCancel={(e) => onPointerRelease(e, 'cancel')}
        onClick={(e) => {
          if (suppressClickRef.current) { suppressClickRef.current = false; return; }
          // A double click's first click also fires this handler; e.detail
          // marks it so onDoubleClick handles it instead and the card never
          // flashes before the lightbox opens.
          if (e.detail === 2) return;
          const hit = hitTest(e);
          if (!hit) return;
          if (hit.badge && goToSuccessor(hit.cell)) return;
          onPick(hit.cell, hit.at);
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
