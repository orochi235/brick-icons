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
