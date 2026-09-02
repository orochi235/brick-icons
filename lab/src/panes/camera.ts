/** The shared 2D camera for a trial's panes.
 *
 * Kept out of the DOM so the fixed-point rule -- the world point under the
 * cursor stays under the cursor across a zoom -- is checked by a test rather
 * than by eye.
 */
export interface Camera {
  zoom: number;
  pan: { x: number; y: number };
}

export const HOME: Camera = { zoom: 1, pan: { x: 0, y: 0 } };
export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 64;

/** labkit hands the view back opaquely, so anything may be in it. */
export function readView(view: unknown): Camera {
  const v = view as Partial<Camera> | undefined;
  if (!v || typeof v.zoom !== 'number' || !Number.isFinite(v.zoom)) return HOME;
  const pan = v.pan;
  if (!pan || !Number.isFinite(pan.x) || !Number.isFinite(pan.y)) return HOME;
  return { zoom: v.zoom, pan: { x: pan.x, y: pan.y } };
}

export function panBy(camera: Camera, dx: number, dy: number): Camera {
  return { zoom: camera.zoom, pan: { x: camera.pan.x + dx, y: camera.pan.y + dy } };
}

/** Scale about a screen point, keeping the world point under it fixed.
 *
 *  `max` is the ceiling the result is clamped to. The loupe passes a higher
 *  one: sharing `MAX_ZOOM` stops the bubble magnifying whenever the shared
 *  camera is near its own limit, which reads as the loupe being broken. */
export function zoomAt(camera: Camera, factor: number, sx: number, sy: number,
                       max: number = MAX_ZOOM): Camera {
  const zoom = Math.min(max, Math.max(MIN_ZOOM, camera.zoom * factor));
  const applied = zoom / camera.zoom;
  return {
    zoom,
    pan: {
      x: sx - (sx - camera.pan.x) * applied,
      y: sy - (sy - camera.pan.y) * applied,
    },
  };
}

export function cssTransform(camera: Camera): string {
  return `translate(${camera.pan.x}px, ${camera.pan.y}px) scale(${camera.zoom})`;
}
