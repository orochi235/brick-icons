import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';

/** The camera reused, not a second notion of position: shift `cam` by the
 *  least amount that brings `rect` fully on screen, one axis at a time.
 *  Already-visible stays untouched, matching the drag/wheel path so a
 *  keyboard move never jumps further than it has to. */
export function panToReveal(rect: Rect, cam: View,
                            viewport: { width: number; height: number }): View {
  const transform = viewToTransform(cam);
  const [dx, dy] = worldToScreen(rect.x, rect.y, transform);
  const dw = rect.w * cam.scale.x;
  const dh = rect.h * cam.scale.y;
  let x = cam.x;
  let y = cam.y;
  if (dx < 0) x = rect.x;
  else if (dx + dw > viewport.width) x = rect.x - (viewport.width - dw) / cam.scale.x;
  if (dy < 0) y = rect.y;
  else if (dy + dh > viewport.height) y = rect.y - (viewport.height - dh) / cam.scale.y;
  return { ...cam, x, y };
}

/** The camera that puts `rect`'s center at the viewport's -- what a search
 *  hit flies to, as opposed to `panToReveal`'s minimum shift for a caret
 *  move that is already mostly on screen.
 *
 *  `minHeightFraction` is a floor, not a target: a jump zooms in far enough
 *  that the cell fills that much of the viewport's height, and leaves the
 *  camera alone if it is already closer. Arriving at a 32px cell in a wall of
 *  24,000 is arriving nowhere.
 *
 *  Zoom first, then center: the offsets are in world units, so they depend on
 *  the scale they are computed against. */
export function centerReveal(rect: Rect, cam: View,
                             viewport: { width: number; height: number },
                             minHeightFraction = 0): View {
  const want = minHeightFraction > 0 && rect.h > 0
    ? (viewport.height * minHeightFraction) / rect.h
    : 0;
  const k = want > cam.scale.y ? want / cam.scale.y : 1;
  const scale = k === 1 ? cam.scale
    : { x: cam.scale.x * k, y: cam.scale.y * k };
  const cx = rect.x + rect.w / 2;
  const cy = rect.y + rect.h / 2;
  return {
    ...cam,
    scale,
    x: cx - viewport.width / 2 / scale.x,
    y: cy - viewport.height / 2 / scale.y,
  };
}
