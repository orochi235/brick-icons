import { clampView, type CanvasSize, type View } from '@weasel-js/core';

export interface WallBounds { w: number; h: number }

/** The blank strip a pan may reach, in screen pixels, when nothing has
 *  measured `--corpus-panel-width` yet. */
export const DEFAULT_BLANK_PX = 272;

/**
 * Clamp a wall camera so a flick or zoom can never lose the wall.
 *
 * Full containment -- the whole wall always on screen -- is the wrong bound:
 * the wall deliberately overflows vertically once fitted to the width, so
 * that rule would fight the fit on every load. Instead the bounds handed to
 * `clampView` are inflated by `blankPx`, the width of a floating panel: a pan
 * can pull the cells hidden under one into the open, and stops there.
 *
 * A wall smaller than the viewport on an axis cannot honor that -- the blank
 * is the viewport minus the wall, whatever the camera does -- so it gets just
 * enough inflation to sit anywhere between the two edges, which leaves the
 * fit's own top-left anchor reachable.
 */
export function clampWallView(view: View, bounds: WallBounds, canvas: CanvasSize,
                               blankPx = DEFAULT_BLANK_PX): View {
  const visW = Math.abs(canvas.width / view.scale.x);
  const visH = Math.abs(canvas.height / view.scale.y);
  const blankW = blankPx / Math.abs(view.scale.x);
  const blankH = blankPx / Math.abs(view.scale.y);
  const marginX = Math.max(blankW, visW - bounds.w, 0);
  const marginY = Math.max(blankH, visH - bounds.h, 0);
  return clampView(view, {
    x: -marginX,
    y: -marginY,
    width: bounds.w + 2 * marginX,
    height: bounds.h + 2 * marginY,
  }, canvas);
}
