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
import { LINKED_BADGE, paintCommands, type Appearance } from '@lab/corpus/paint';
import { cornerBadgeAt, drawPaintCommand } from '@lab/corpus/draw2d';
import { scenePainter, type SceneWallPainter } from '@lab/corpus/drawScene';
import { DEFAULT_PALETTE, readPalette, type CellState, type Palette } from '@lab/corpus/palette';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { pinchStep } from '@lab/corpus/pinch';
import { centerReveal, panToReveal } from '@lab/corpus/reveal';
import type { RampName, TintMode } from '@lab/corpus/tint';
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
  /** Paint cell bodies with weasel instead of Canvas2D. The overlays are
   *  Canvas2D either way, on a layer above. */
  sceneRenderer?: boolean;
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
  /** These cells belong to a slot the toolbar has already moved off. */
  stale?: boolean;
  /** Group headers the layout asked for. Absent for a dense grid. */
  bands?: Band[];
  /** How much sharper than `devicePixelRatio` to draw, for a pinch the page
   *  cannot otherwise see. 1 everywhere but a pinched Chrome. */
  pixelScale?: number;
  /** What a cell's color says. Outside `status` the thumbnail gives way to
   *  the ramp. */
  tint?: TintMode;
  gradient?: RampName;
}

function ongoingInvoker(action: typeof viewportDragPanAction) {
  if (!action.invoker || action.invoker.timing !== 'ongoing') {
    throw new Error('viewport.dragPan: expected an ongoing invoker');
  }
  return action.invoker;
}

const NOOP_MODIFIERS = { alt: false, ctrl: false, meta: false, shift: false };


/** The wall's only rendering surface.
 *
 *  Canvas2D holds today's corpus. When weasel's mega view exists this body is
 *  what it replaces; nothing above it knows what an atlas page is. */
export function Wall({ cells, rects, cam, sheet, manifest, loose, vector, width, height,
                       highlight, highlightTag, explicitCaret, onExplicitCaretChange,
                       onPan, onPick, onOpen, onDragStart,
                       dragThresholdPx = DEFAULT_PARAMS.dragThresholdPx,
                       pixelScale = 1, appearance, bands, tint, gradient, stale = false,
                       sceneRenderer = false }: WallProps) {
  const ref = useRef<HTMLCanvasElement>(null);
  const glRef = useRef<HTMLCanvasElement>(null);
  const painterRef = useRef<{ painter: SceneWallPainter;
                              gl: HTMLCanvasElement } | null>(null);
  const [sheetBitmap, setSheetBitmap] = useState<ImageBitmap | null>(null);
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
   *  caret on it and center it. Centered rather than an arrow key's minimum
   *  shift -- the successor is somewhere else in the wall entirely, and
   *  landing it against an edge leaves the reader hunting for what they
   *  asked to be taken to. */
  const goToSuccessor = (cell: Cell): boolean => {
    if (!cell.successor) return false;
    const next = byId.get(cell.successor);
    if (next == null) return false;
    onExplicitCaretChange(next);
    const rect = rects[next];
    if (rect) onPan(centerReveal(rect, camRef.current, { width, height }));
    return true;
  };

  const caretIndex = explicitCaret ?? implied;
  const caretCell = caretIndex != null ? cells[caretIndex] : undefined;

  // Weasel takes a texture, not an <img>. Never closed: a paint can still be
  // holding the previous one when a slot swap replaces it, and a closed bitmap
  // draws nothing with no error anywhere.
  useEffect(() => {
    if (!sceneRenderer || !sheet) { setSheetBitmap(null); return; }
    let live = true;
    void createImageBitmap(sheet)
      .then((b) => { if (live) setSheetBitmap(b); })
      .catch(() => { if (live) setSheetBitmap(null); });
    return () => { live = false; };
  }, [sceneRenderer, sheet]);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    // Times the pinch, not just the device: Chrome's pinch zoom magnifies the
    // composited layer without moving `devicePixelRatio`, so a store sized off
    // dpr alone is blown up by the compositor and the cells go soft. Picking a
    // sharper tile without this buys nothing -- it is downsampled straight back
    // into the same device pixels.
    const dpr = (window.devicePixelRatio || 1) * pixelScale;
    const cmds = paintCommands({
      cells, rects, visible, cam, manifest, palette, loose, vector, highlight, highlightTag,
      caret: caretIndex,
      appearance, bands, tint, gradient, stale,
    });

    const gl = glRef.current;
    if (sceneRenderer && gl) {
      if (painterRef.current?.gl !== gl) {
        painterRef.current = { painter: scenePainter(gl, canvas), gl };
      }
      // Linear, not the bench's nearest: the 2D path draws with
      // `imageSmoothingEnabled`, and matching it halves the drift against the
      // renderer this replaces -- mean |delta| 1.33 against 2.56 over a
      // magnified wall, with no cell-edge bleed at either setting.
      painterRef.current.painter.paint(cmds, { width, height, dpr },
                                       { bitmap: sheetBitmap, img: sheet }, palette, 'linear');
      return;
    }

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    // The backing store is oversized for sharpness; without pinning the CSS
    // size back down the canvas displays at the backing-store size and
    // overflows its container on any dpr != 1.
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = true;
    for (const cmd of cmds) drawPaintCommand(ctx, cmd, sheet, palette);
  }, [cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, highlightTag,
      caretIndex,
      appearance, bands, tint, gradient, stale, width, height, pixelScale, sceneRenderer, sheetBitmap]);

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
      appearance, bands, tint, gradient, stale,
    })) {
      drawPaintCommand(ctx, cmd, sheet, palette, offset);
    }
  }, [loupe.visible, loupe.aim, loupe.factor, loupeCapability.diameter,
      cells, rects, visible, cam, sheet, manifest, palette, loose, vector, highlight, caretIndex,
      appearance, bands, tint, gradient, stale, width, height]);

  const hitTest = (e: { clientX: number; clientY: number;
                         currentTarget: HTMLCanvasElement }) => {
    const [sx, sy] = clientToCanvas(e.currentTarget, e.clientX, e.clientY);
    const visible = visibleRange(rects, cam, { width, height });
    // `appearance` and not the default: with badges switched off the command
    // carries none, and a click must not find one the wall never drew.
    const cmds = paintCommands({ cells, rects, visible, cam, manifest, palette,
                                 appearance });
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
      <div className="corpus-canvas-stack">
      {sceneRenderer && <canvas ref={glRef} className="corpus-canvas-gl" />}
      <canvas
        ref={ref}
        className={[
          'corpus-canvas',
          dragging ? 'corpus-canvas-dragging' : '',
          sceneRenderer ? 'corpus-canvas-over' : '',
        ].filter(Boolean).join(' ')}
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
      </div>
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
