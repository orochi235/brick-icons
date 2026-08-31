import type { Camera } from '@lab/panes/camera';

/** A rectangle in fractions of the render box. Survives a change of
 *  --render-px; does NOT survive a change of --angle, which is why a defect
 *  also records the parameters it was seen at. */
export interface Mark {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Box {
  width: number;
  height: number;
}

export interface ScreenRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Smaller than this is a stray click, not a mark. */
const MIN_SIDE = 0.004;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

function screenToFraction(point: { x: number; y: number }, box: Box, camera: Camera) {
  return {
    x: clamp01((point.x - camera.pan.x) / camera.zoom / box.width),
    y: clamp01((point.y - camera.pan.y) / camera.zoom / box.height),
  };
}

export function markFromDrag(start: { x: number; y: number },
                             end: { x: number; y: number },
                             box: Box, camera: Camera): Mark {
  const a = screenToFraction(start, box, camera);
  const b = screenToFraction(end, box, camera);
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(b.x - a.x),
    h: Math.abs(b.y - a.y),
  };
}

export function markToScreen(mark: Mark, box: Box, camera: Camera): ScreenRect {
  return {
    left: mark.x * box.width * camera.zoom + camera.pan.x,
    top: mark.y * box.height * camera.zoom + camera.pan.y,
    width: mark.w * box.width * camera.zoom,
    height: mark.h * box.height * camera.zoom,
  };
}

const round4 = (v: number) => Math.round(v * 10000) / 10000;

/** Null for a mark too small to have been meant. */
export function normalizeMark(mark: Mark): Mark | null {
  if (mark.w < MIN_SIDE || mark.h < MIN_SIDE) return null;
  return { x: round4(mark.x), y: round4(mark.y), w: round4(mark.w), h: round4(mark.h) };
}
