import { screenToWorld, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';

/** Indices of the rects touching the viewport.
 *
 *  A linear scan, deliberately: it is layout-agnostic, and 24,591 rects cost
 *  well under a millisecond. A spatial index is what a non-uniform layout
 *  would need, not what this scale needs.
 *
 *  `viewport` may carry an origin, in the same CSS pixels as its size and
 *  measured from the canvas's own top-left. A pinch leaves only part of the
 *  canvas on screen, and that part is not at its corner; without the origin
 *  the range covers the whole canvas, which is how a pinched wall would fetch
 *  a sharper tile for every cell including the ones nobody can see. */
export function visibleRange(rects: readonly Rect[], view: View,
                             viewport: { width: number; height: number;
                                         x?: number; y?: number }):
                             number[] {
  const transform = viewToTransform(view);
  const x0 = viewport.x ?? 0, y0 = viewport.y ?? 0;
  const [tlX, tlY] = screenToWorld(x0, y0, transform);
  const [brX, brY] = screenToWorld(x0 + viewport.width, y0 + viewport.height,
                                   transform);
  const out: number[] = [];
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i]!;
    if (r.x < brX && r.x + r.w > tlX && r.y < brY && r.y + r.h > tlY) {
      out.push(i);
    }
  }
  return out;
}
