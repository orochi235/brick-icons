import { describe, expect, it } from 'vitest';
import { clampWallView, DEFAULT_BLANK_PX } from '@lab/corpus/clamp';

const BOUNDS = { w: 1000, h: 800 };
const CANVAS = { width: 400, height: 300 };

describe('clampWallView', () => {
  it('leaves a view inside the slack untouched', () => {
    const v = { x: 100, y: 100, scale: { x: 1, y: 1 } };
    expect(clampWallView(v, BOUNDS, CANVAS)).toBe(v);
  });

  it('stops a rightward flick a panel-width past the wall', () => {
    const out = clampWallView({ x: 9999, y: 100, scale: { x: 1, y: 1 } }, BOUNDS, CANVAS, 120);
    expect(out.x + CANVAS.width - BOUNDS.w).toBeCloseTo(120);
  });

  it('stops a leftward flick the same way', () => {
    const out = clampWallView({ x: -9999, y: 100, scale: { x: 1, y: 1 } }, BOUNDS, CANVAS, 120);
    expect(-out.x).toBeCloseTo(120);
  });

  it('does the same on the vertical axis', () => {
    const down = clampWallView({ x: 100, y: 9999, scale: { x: 1, y: 1 } }, BOUNDS, CANVAS, 120);
    expect(down.y + CANVAS.height - BOUNDS.h).toBeCloseTo(120);
    const up = clampWallView({ x: 100, y: -9999, scale: { x: 1, y: 1 } }, BOUNDS, CANVAS, 120);
    expect(-up.y).toBeCloseTo(120);
  });

  it('defaults to a panel width when nobody has measured one', () => {
    const out = clampWallView({ x: 9999, y: 100, scale: { x: 1, y: 1 } }, BOUNDS, CANVAS);
    expect(out.x + CANVAS.width - BOUNDS.w).toBeCloseTo(DEFAULT_BLANK_PX);
  });

  it('lets a wall too small to fill the frame reach either edge, and no further', () => {
    const small = { w: 100, h: 60 };
    const back = clampWallView({ x: -9999, y: -9999, scale: { x: 1, y: 1 } }, small, CANVAS, 120);
    expect(back.x).toBeCloseTo(small.w - CANVAS.width);
    expect(back.y).toBeCloseTo(small.h - CANVAS.height);
    // and the fit's own anchor, top-left at the frame's, stays reachable
    const anchored = { x: 0, y: 0, scale: { x: 1, y: 1 } };
    expect(clampWallView(anchored, small, CANVAS, 120)).toBe(anchored);
  });

  it('holds the blank strip at a constant width on screen, whatever the zoom', () => {
    // the allowance is in screen pixels, so at scale 2 it is half as many
    // world units and the strip still looks the same size
    const out = clampWallView({ x: 9999, y: 100, scale: { x: 2, y: 2 } }, BOUNDS, CANVAS, 120);
    expect(out.x + CANVAS.width / 2 - BOUNDS.w).toBeCloseTo(120 / 2);
  });
});
