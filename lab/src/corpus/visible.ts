import type { Camera } from '@lab/corpus/camera';
import { toWorld } from '@lab/corpus/camera';
import type { Rect } from '@lab/corpus/layout';

/** Indices of the rects touching the viewport.
 *
 *  A linear scan, deliberately: it is layout-agnostic, and 24,591 rects cost
 *  well under a millisecond. A spatial index is what a non-uniform layout
 *  would need, not what this scale needs. */
export function visibleRange(rects: readonly Rect[], cam: Camera,
                             viewport: { width: number; height: number }):
                             number[] {
  const tl = toWorld(cam, 0, 0);
  const br = toWorld(cam, viewport.width, viewport.height);
  const out: number[] = [];
  for (let i = 0; i < rects.length; i++) {
    const r = rects[i]!;
    if (r.x < br.x && r.x + r.w > tl.x && r.y < br.y && r.y + r.h > tl.y) {
      out.push(i);
    }
  }
  return out;
}
