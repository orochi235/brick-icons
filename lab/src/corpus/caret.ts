import { worldToScreen, viewToTransform, type View } from '@weasel-js/core';
import type { Rect } from '@lab/corpus/layout';

export type Direction = 'up' | 'down' | 'left' | 'right';

/** The cell with the most on-screen area, ties broken by distance from the
 *  viewport center -- the implied caret when nothing has made one explicit. */
export function impliedCaret(rects: readonly Rect[], visible: readonly number[],
                             cam: View, viewport: { width: number; height: number }):
                             number | null {
  const transform = viewToTransform(cam);
  const centerX = viewport.width / 2;
  const centerY = viewport.height / 2;
  let best: { i: number; area: number; distSq: number } | null = null;
  for (const i of visible) {
    const r = rects[i];
    if (!r) continue;
    const [dx, dy] = worldToScreen(r.x, r.y, transform);
    const dw = r.w * cam.scale.x;
    const dh = r.h * cam.scale.y;
    const x0 = Math.max(0, dx);
    const y0 = Math.max(0, dy);
    const x1 = Math.min(viewport.width, dx + dw);
    const y1 = Math.min(viewport.height, dy + dh);
    const area = Math.max(0, x1 - x0) * Math.max(0, y1 - y0);
    const cx = dx + dw / 2;
    const cy = dy + dh / 2;
    const distSq = (cx - centerX) ** 2 + (cy - centerY) ** 2;
    if (!best || area > best.area || (area === best.area && distSq < best.distSq)) {
      best = { i, area, distSq };
    }
  }
  return best ? best.i : null;
}

function center(r: Rect): { x: number; y: number } {
  return { x: r.x + r.w / 2, y: r.y + r.h / 2 };
}

// Cross-axis drift is penalized well past its raw distance, so a same-row
// (or same-column) cell wins over a diagonal one that is merely nearer as
// the crow flies -- see caret.test.ts's "nearer diagonal" case.
const CROSS_PENALTY = 3;

/** The nearest cell whose center lies in `direction` from `from`'s -- scored
 *  by distance along the direction plus a penalty for drifting across it,
 *  not by array position. `null` when no cell lies that way at all. */
function geometricNeighbor(rects: readonly Rect[], from: number,
                           direction: Direction): number | null {
  const cur = rects[from];
  if (!cur) return null;
  const c0 = center(cur);
  let best: { i: number; score: number } | null = null;
  for (let i = 0; i < rects.length; i++) {
    if (i === from) continue;
    const r = rects[i];
    if (!r) continue;
    const c = center(r);
    let primary: number;
    let cross: number;
    switch (direction) {
      case 'right': primary = c.x - c0.x; cross = Math.abs(c.y - c0.y); break;
      case 'left': primary = c0.x - c.x; cross = Math.abs(c.y - c0.y); break;
      case 'down': primary = c.y - c0.y; cross = Math.abs(c.x - c0.x); break;
      case 'up': primary = c0.y - c.y; cross = Math.abs(c.x - c0.x); break;
    }
    if (primary <= 0) continue;
    const score = primary + CROSS_PENALTY * cross;
    if (!best || score < best.score) best = { i, score };
  }
  return best ? best.i : null;
}

/** The caret's next index moving `direction` from `from`.
 *
 *  Geometric first -- the nearest cell that direction, not `from +- 1` --
 *  because a grouped layout inserts whitespace that grid arithmetic can't
 *  see. Left/right fall back to array order at a row's end, the one
 *  continuation a reader means by "wrap"; up/down have no such reading and
 *  return `null` instead of guessing. */
export function adjacent(rects: readonly Rect[], from: number,
                         direction: Direction): number | null {
  const geo = geometricNeighbor(rects, from, direction);
  if (geo !== null) return geo;
  if (direction === 'right') return from + 1 < rects.length ? from + 1 : null;
  if (direction === 'left') return from - 1 >= 0 ? from - 1 : null;
  return null;
}
