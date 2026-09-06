import { screenToWorld, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';

/** Indices of the rects touching the viewport.
 *
 *  A linear scan, deliberately: it is layout-agnostic, and 24,591 rects cost
 *  well under a millisecond. A spatial index is what a non-uniform layout
 *  would need, not what this scale needs. */
export function visibleRange(rects: readonly Rect[], view: View,
                             viewport: { width: number; height: number }):
                             number[] {
  const transform = viewToTransform(view);
  const [tlX, tlY] = screenToWorld(0, 0, transform);
  const [brX, brY] = screenToWorld(viewport.width, viewport.height, transform);
  const out: number[] = [];
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i]!;
    if (r.x < brX && r.x + r.w > tlX && r.y < brY && r.y + r.h > tlY) {
      out.push(i);
    }
  }
  return out;
}
