/** The loupe: a magnified window on one pane's drawing, following the cursor.
 *
 * Kept out of the DOM for the reason `camera.ts` is -- the rule that the point
 * under the cursor is the point at the bubble's centre is then checked by a
 * test rather than by eye.
 */
import { HOME, type Camera, zoomAt } from '@lab/panes/camera';
import type { Source, SourceKind } from '@lab/panes/sources';

export const MIN_FACTOR = 2;
export const MAX_FACTOR = 16;
export const DEFAULT_FACTOR = 6;

/** Above `camera.MAX_ZOOM` on purpose: sharing that ceiling stops the bubble
 *  magnifying once the shared camera is near its own limit. */
export const MAX_LOUPE_ZOOM = 1024;

const DIAMETER_FRACTION = 0.4;
const MIN_DIAMETER = 120;
const MAX_DIAMETER = 320;

/** The panes drawing one viewBox at one size, so one body coordinate is one
 *  world point across all of them. */
const MIRRORS: ReadonlySet<SourceKind> = new Set<SourceKind>(['engine', 'diff']);

export interface Box { width: number; height: number }
export interface Point { x: number; y: number }

export function clampFactor(factor: number): number {
  if (!Number.isFinite(factor)) return DEFAULT_FACTOR;
  return Math.min(MAX_FACTOR, Math.max(MIN_FACTOR, factor));
}

export function loupeCamera(camera: Camera, factor: number, at: Point): Camera {
  return zoomAt(camera, clampFactor(factor), at.x, at.y, MAX_LOUPE_ZOOM);
}

/** The bubble's camera for content that already has the shared camera in it.
 *  The 3D pane renders into its frustum rather than being transformed by CSS,
 *  so composing the camera again magnifies by zoom x factor and points at the
 *  wrong place. */
export function loupeCameraForImage(factor: number, at: Point): Camera {
  return zoomAt(HOME, clampFactor(factor), at.x, at.y, MAX_LOUPE_ZOOM);
}

export function bubbleDiameter(box: Box): number {
  const short = Math.min(box.width, box.height);
  return Math.min(MAX_DIAMETER, Math.max(MIN_DIAMETER, short * DIAMETER_FRACTION));
}

/** Where the magnified stage sits inside the bubble: the pane body, shifted so
 *  the cursor's own point lands at the bubble's centre. */
export function stageOffset(at: Point, diameter: number): Point {
  return { x: diameter / 2 - at.x, y: diameter / 2 - at.y };
}

/** Whether `source` draws a bubble for a pointer sitting in `over`. */
export function showsLoupe(source: Source, over: Source | null,
                           allPanes: boolean): boolean {
  if (!over) return false;
  if (source.id === over.id) return true;
  return allPanes && MIRRORS.has(source.kind) && MIRRORS.has(over.kind);
}
