import { describe, expect, it } from 'vitest';
import { clampWallView } from '@lab/corpus/clamp';

const BOUNDS = { w: 1000, h: 800 };
const CANVAS = { width: 400, height: 300 };
const PITCH = 36;

describe('clampWallView', () => {
  it('leaves a view inside the slack untouched', () => {
    const v = { x: 100, y: 100, scale: { x: 1, y: 1 } };
    expect(clampWallView(v, BOUNDS, CANVAS, PITCH)).toBe(v);
  });

  it('stops a rightward flick with one pitch of the wall still on screen', () => {
    const v = { x: 9999, y: 100, scale: { x: 1, y: 1 } };
    const out = clampWallView(v, BOUNDS, CANVAS, PITCH);
    // maxX = bounds.w - pitch: the last pitch-wide strip stays visible.
    expect(out.x).toBe(BOUNDS.w - PITCH);
  });

  it('stops a leftward flick with one pitch of the wall still on screen', () => {
    const v = { x: -9999, y: 100, scale: { x: 1, y: 1 } };
    const out = clampWallView(v, BOUNDS, CANVAS, PITCH);
    // minX = pitch - visW: the view can run into blank space, but the first
    // pitch-wide strip of the wall never leaves the right edge of the frame.
    expect(out.x).toBe(PITCH - CANVAS.width);
  });

  it('does the same on the vertical axis', () => {
    const down = clampWallView({ x: 100, y: 9999, scale: { x: 1, y: 1 } },
                                BOUNDS, CANVAS, PITCH);
    expect(down.y).toBe(BOUNDS.h - PITCH);
    const up = clampWallView({ x: 100, y: -9999, scale: { x: 1, y: 1 } },
                              BOUNDS, CANVAS, PITCH);
    expect(up.y).toBe(PITCH - CANVAS.height);
  });

  it('falls back to full containment once zoomed past one pitch', () => {
    // scale 20 -> visible 20x15, already smaller than one pitch: no slack
    // is needed, so clamping keeps the viewport fully inside the wall.
    const scale = { x: 20, y: 20 };
    const right = clampWallView({ x: 9999, y: 0, scale }, BOUNDS, CANVAS, PITCH);
    expect(right.x).toBe(BOUNDS.w - CANVAS.width / 20);
    const left = clampWallView({ x: -9999, y: 0, scale }, BOUNDS, CANVAS, PITCH);
    expect(left.x).toBeCloseTo(0);
  });

  it('keeps the margin independent of zoom level once zoomed out', () => {
    // Zoomed further out (visW=4000) still yields the same maxX -- only the
    // near-edge margin (visW-dependent) moves, not the far one.
    const scale = { x: 0.1, y: 0.1 };
    const out = clampWallView({ x: 9999, y: 0, scale }, BOUNDS, CANVAS, PITCH);
    expect(out.x).toBe(BOUNDS.w - PITCH);
  });

  it('never displaces a wall already shorter than one pitch', () => {
    // A 2-cell corpus (as in a test fixture) is far shorter than a 36px
    // pitch on the row axis; the fit's chosen anchor must survive untouched.
    const tinyBounds = { w: 68, h: 32 };
    const canvas = { width: 800, height: 600 };
    const v = { x: 0, y: 0, scale: { x: 10, y: 10 } };
    expect(clampWallView(v, tinyBounds, canvas, PITCH)).toBe(v);
  });
});
