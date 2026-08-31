import { describe, expect, it } from 'vitest';
import { markFromDrag, markToScreen, normalizeMark } from '@lab/defects/geometry';
import { HOME } from '@lab/panes/camera';

const BOX = { width: 200, height: 100 };

describe('markFromDrag', () => {
  it('converts a drag to fractions of the render box', () => {
    const mark = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    // A raw drag carries binary-float noise; rounding is normalizeMark's job.
    expect(mark).toEqual({ x: 0.1, y: 0.1, w: expect.closeTo(0.2), h: expect.closeTo(0.2) });
  });

  it('normalizes a drag made right-to-left', () => {
    const forward = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    const backward = markFromDrag({ x: 60, y: 30 }, { x: 20, y: 10 }, BOX, HOME);
    expect(backward).toEqual(forward);
  });

  it('undoes the camera, so a mark made zoomed in lands where it was drawn', () => {
    const camera = { zoom: 2, pan: { x: -40, y: -20 } };
    // screen 0,0 is world 20,10 at this camera
    const mark = markFromDrag({ x: 0, y: 0 }, { x: 40, y: 40 }, BOX, camera);
    expect(mark).toEqual({ x: 0.1, y: 0.1, w: 0.1, h: expect.closeTo(0.2) });
  });

  it('clamps to the render box', () => {
    const mark = markFromDrag({ x: -50, y: -50 }, { x: 400, y: 400 }, BOX, HOME);
    expect(mark).toEqual({ x: 0, y: 0, w: 1, h: 1 });
  });
});

describe('markToScreen', () => {
  it('is the inverse of markFromDrag at home', () => {
    const mark = markFromDrag({ x: 20, y: 10 }, { x: 60, y: 30 }, BOX, HOME);
    expect(markToScreen(mark, BOX, HOME))
      .toEqual({ left: 20, top: 10, width: 40, height: 20 });
  });

  // The drag is inside the render box at this camera. A drag that starts off
  // the box is clamped and cannot round-trip, which is the point of clamping.
  it('is the inverse under a camera too', () => {
    const camera = { zoom: 3, pan: { x: 17, y: 9 } };
    const mark = markFromDrag({ x: 20, y: 15 }, { x: 80, y: 45 }, BOX, camera);
    const screen = markToScreen(mark, BOX, camera);
    expect(screen.left).toBeCloseTo(20);
    expect(screen.top).toBeCloseTo(15);
    expect(screen.width).toBeCloseTo(60);
    expect(screen.height).toBeCloseTo(30);
  });

  it('grows with zoom', () => {
    const mark = { x: 0.25, y: 0.25, w: 0.5, h: 0.5 };
    const at1 = markToScreen(mark, BOX, HOME);
    const at2 = markToScreen(mark, BOX, { zoom: 2, pan: { x: 0, y: 0 } });
    expect(at2.width).toBe(at1.width * 2);
  });
});

describe('normalizeMark', () => {
  it('rounds to four places, which is finer than a pixel on any render', () => {
    expect(normalizeMark({ x: 0.123456, y: 0.5, w: 0.2, h: 0.2 })!.x).toBe(0.1235);
  });

  it('rejects a zero-area mark', () => {
    expect(normalizeMark({ x: 0.1, y: 0.1, w: 0, h: 0.2 })).toBeNull();
  });

  it('rejects a mark below the minimum size, which is a stray click', () => {
    expect(normalizeMark({ x: 0.1, y: 0.1, w: 0.001, h: 0.001 })).toBeNull();
  });
});
