import { clampView, type CanvasSize, type View } from '@weasel-js/core';

export interface WallBounds { w: number; h: number }

/**
 * Clamp a wall camera so a flick or zoom can never lose the wall.
 *
 * Full containment -- the whole wall always on screen -- is the wrong bound:
 * the wall deliberately overflows vertically once fitted to the width, so
 * that rule would fight the fit on every load. Instead, inflate the bounds
 * passed to `clampView` by (visible extent - one cell pitch) on each axis,
 * so the pan can run all the way to blank space but always leaves at least
 * one pitch-wide strip of the wall on screen.
 */
export function clampWallView(view: View, bounds: WallBounds, canvas: CanvasSize,
                               pitch: number): View {
  const visW = Math.abs(canvas.width / view.scale.x);
  const visH = Math.abs(canvas.height / view.scale.y);
  // A wall shorter than one pitch (a handful of cells, as in a test fixture)
  // can't offer a whole pitch on that axis -- demand the whole axis instead,
  // or the margin below would overshoot and shove an already-fitting wall
  // off its anchor.
  const pitchX = Math.min(pitch, bounds.w);
  const pitchY = Math.min(pitch, bounds.h);
  const marginX = Math.max(0, visW - pitchX);
  const marginY = Math.max(0, visH - pitchY);
  return clampView(view, {
    x: -marginX,
    y: -marginY,
    width: bounds.w + 2 * marginX,
    height: bounds.h + 2 * marginY,
  }, canvas);
}
