export interface Camera { x: number; y: number; scale: number }

export const MIN_SCALE = 0.01;
export const MAX_SCALE = 64;

/** The on-screen cell size each baked level is meant to cover. */
const BANDS: readonly [number, number][] = [[8, 16], [32, 64], [128, Infinity]];

export function toScreen(cam: Camera, x: number, y: number) {
  return { x: (x - cam.x) * cam.scale, y: (y - cam.y) * cam.scale };
}

export function toWorld(cam: Camera, sx: number, sy: number) {
  return { x: sx / cam.scale + cam.x, y: sy / cam.scale + cam.y };
}

export function zoomAt(cam: Camera, sx: number, sy: number,
                       factor: number): Camera {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, cam.scale * factor));
  const before = toWorld(cam, sx, sy);
  const after = toWorld({ ...cam, scale }, sx, sy);
  return { x: cam.x + before.x - after.x, y: cam.y + before.y - after.y, scale };
}

export function fitBounds(bounds: { w: number; h: number },
                          viewport: { width: number; height: number }): Camera {
  // An empty wall has zero bounds, and the unguarded division hands back
  // Infinity -- which multiplies every coordinate into NaN with nothing
  // downstream to catch it.
  if (bounds.w <= 0 || bounds.h <= 0) return { x: 0, y: 0, scale: 1 };
  const scale = Math.min(viewport.width / bounds.w, viewport.height / bounds.h);
  return { x: 0, y: 0, scale };
}

/** The level a cell of `px` on screen wants, ignoring what is loaded. */
export function levelFor(px: number): number {
  for (const [level, top] of BANDS) if (px < top) return level;
  return BANDS[BANDS.length - 1]![0];
}

/** The level to actually use, given the one in hand.
 *
 *  Straight thresholds re-upload every frame when a zoom parks on a boundary,
 *  so a level is kept until the cell size is half again past its band. */
export function pickLevel(current: number, px: number): number {
  const wanted = levelFor(px);
  if (wanted === current) return current;
  return wanted > current
    ? (levelFor(px / 1.5) > current ? wanted : current)
    : (levelFor(px / 0.67) < current ? wanted : current);
}
