import { describe, expect, it } from 'vitest';
import { HOME, panBy, zoomAt } from '@lab/panes/camera';
import { orbitFromAngle } from '@lab/panes/orbit';
import {
  eyeFor, fromScreen, frustum, isRenderFit, letterbox, lightPosition,
  partColorHex, screenMap, strokePx, threeStyle, toScreen, toThree,
  type RenderFit, type Vec3Tuple,
} from '@lab/panes/viewport';

/** `brick-icons 3005 --shading outline --format svg`, verbatim. Real numbers
 *  rather than made-up ones: the basis is what the engine actually projects
 *  the iso pose with. */
const FIT_3005: RenderFit = {
  right: [0.7071067811865477, 0.0, 0.7071067811865475],
  up: [-0.3535533905932737, -0.8660254037844387, 0.3535533905932738],
  fwd: [-0.6123724356957945, 0.49999999999999994, 0.6123724356957946],
  k: 4.523753890521988,
  kx: 128.0,
  ky: 37.98777052407124,
  width: 256,
  height: 170,
};

/** A canvas whose units are pixels and whose origin is its corner, so an
 *  expectation reads as arithmetic rather than as a fixture lookup. */
const UNIT: RenderFit = {
  right: [1, 0, 0], up: [0, 1, 0], fwd: [0, 0, 1],
  k: 1, kx: 0, ky: 0, width: 100, height: 100,
};

describe('isRenderFit', () => {
  it('accepts what the CLI writes', () => {
    expect(isRenderFit(FIT_3005)).toBe(true);
  });

  it('rejects a partial or degenerate fit rather than drawing with NaN', () => {
    expect(isRenderFit(undefined)).toBe(false);
    expect(isRenderFit({ ...FIT_3005, right: [1, 2] })).toBe(false);
    expect(isRenderFit({ ...FIT_3005, k: 0 })).toBe(false);
    expect(isRenderFit({ ...FIT_3005, width: 0 })).toBe(false);
  });
});

describe('letterbox', () => {
  it('fits the short axis and centres on the long one, as `meet` does', () => {
    const box = { width: 400, height: 200 };
    const fitted = letterbox(UNIT, box);
    expect(fitted.scale).toBe(2);
    expect(fitted.x).toBe(100);
    expect(fitted.y).toBe(0);
  });

  it('centres a landscape viewBox vertically in a square pane', () => {
    const fitted = letterbox(FIT_3005, { width: 512, height: 512 });
    expect(fitted.scale).toBeCloseTo(2);
    expect(fitted.x).toBeCloseTo(0);
    expect(fitted.y).toBeCloseTo((512 - 170 * 2) / 2);
  });
});

describe('screenMap', () => {
  it('puts the viewBox centre at the pane centre at home', () => {
    const box = { width: 512, height: 512 };
    const map = screenMap(FIT_3005, box, HOME);
    // The A/B that the fit sends to the middle of the viewBox.
    const a = (FIT_3005.width / 2 - FIT_3005.kx) / FIT_3005.k;
    const b = (FIT_3005.height / 2 - FIT_3005.ky) / FIT_3005.k;
    const p = toScreen(map, a, b);
    expect(p.x).toBeCloseTo(256);
    expect(p.y).toBeCloseTo(256);
  });

  it('moves a pan straight across the screen', () => {
    const box = { width: 300, height: 300 };
    const at = (camera: typeof HOME) => toScreen(screenMap(UNIT, box, camera), 10, 20);
    const home = at(HOME);
    const panned = at(panBy(HOME, 30, -12));
    expect(panned.x - home.x).toBeCloseTo(30);
    expect(panned.y - home.y).toBeCloseTo(-12);
  });

  it('keeps the point under the cursor fixed across a zoom', () => {
    const box = { width: 400, height: 260 };
    const before = screenMap(FIT_3005, box, HOME);
    const under = fromScreen(before, 130, 90);
    const after = screenMap(FIT_3005, box, zoomAt(HOME, 2.5, 130, 90));
    const moved = toScreen(after, under.a, under.b);
    expect(moved.x).toBeCloseTo(130);
    expect(moved.y).toBeCloseTo(90);
  });
});

describe('frustum', () => {
  it('spans the pane in projected units', () => {
    const f = frustum(UNIT, { width: 100, height: 100 }, HOME);
    expect(f.left).toBeCloseTo(0);
    expect(f.right).toBeCloseTo(100);
    // B is screen-down and camera-up is its negation, so the top is the larger.
    expect(f.top).toBeCloseTo(0);
    expect(f.bottom).toBeCloseTo(-100);
    expect(f.top).toBeGreaterThan(f.bottom);
  });

  it('halves its extent when the zoom doubles', () => {
    const box = { width: 400, height: 400 };
    const home = frustum(FIT_3005, box, HOME);
    const closer = frustum(FIT_3005, box, { zoom: 2, pan: { x: 0, y: 0 } });
    expect(closer.right - closer.left).toBeCloseTo((home.right - home.left) / 2);
    expect(closer.top - closer.bottom).toBeCloseTo((home.top - home.bottom) / 2);
  });
});

describe('eyeFor', () => {
  it('stands the eye back along the view axis', () => {
    const target: Vec3Tuple = [3, 4, 5];
    const eye = eyeFor(FIT_3005, target, 100);
    eye.forEach((coord, i) => {
      expect(coord).toBeCloseTo((target[i] ?? 0) - (FIT_3005.fwd[i] ?? 0) * 100);
    });
  });
});

describe('toThree', () => {
  it('agrees with the orbit control about where an angle puts the camera', () => {
    // The drift guard: `orbitFromAngle` is the lab's own angle -> position map
    // and `fwd` is the engine's, derived independently. A pose reached by
    // either route must be the same pose, or a drag would jump the render.
    const [ex, ey, ez] = toThree(eyeFor(FIT_3005, [0, 0, 0], 1));
    const orbit = orbitFromAngle({ lat: 30, long: 45 }, 1);
    expect(ex).toBeCloseTo(orbit.x);
    expect(ey).toBeCloseTo(orbit.y);
    expect(ez).toBeCloseTo(orbit.z);
  });

  it('is its own inverse', () => {
    expect(toThree(toThree([1, 2, 3]))).toEqual([1, 2, 3]);
  });
});

describe('strokePx', () => {
  it('scales a viewBox-unit stroke by the letterbox and the zoom, as CSS does', () => {
    const box = { width: 512, height: 512 };
    // A 256-wide viewBox letterboxes into a 512 pane at 2x.
    expect(strokePx(FIT_3005, box, HOME, 2)).toBeCloseTo(4);
    expect(strokePx(FIT_3005, box, { zoom: 3, pan: { x: 0, y: 0 } }, 2)).toBeCloseTo(12);
  });

  it('leaves the width alone with no fit to scale by', () => {
    expect(strokePx(null, { width: 512, height: 512 }, HOME, 2)).toBe(2);
  });

  it('never thins a stroke out of existence', () => {
    expect(strokePx(FIT_3005, { width: 4, height: 4 },
                    { zoom: 0.1, pan: { x: 0, y: 0 } }, 1)).toBeGreaterThan(0);
  });
});

describe('lightPosition', () => {
  const lit: RenderFit = { ...FIT_3005, light: [-0.5, 0.6, -0.62] };

  it('is null when the render had no style to report one', () => {
    expect(lightPosition(FIT_3005, 100)).toBeNull();
  });

  it('turns the view-space direction into the pane world, at the distance', () => {
    const p = lightPosition(lit, 100)!;
    expect(Math.hypot(p[0], p[1], p[2])).toBeCloseTo(100 * Math.hypot(-0.5, 0.6, -0.62));
  });

  it('puts a light shining from the viewer where the camera is', () => {
    // View-space (0, 0, -1) points back down the view axis, at the viewer.
    const head: RenderFit = { ...FIT_3005, light: [0, 0, -1] };
    const p = lightPosition(head, 1)!;
    const eye = toThree(eyeFor(FIT_3005, [0, 0, 0], 1));
    expect(p[0]).toBeCloseTo(eye[0]);
    expect(p[1]).toBeCloseTo(eye[1]);
    expect(p[2]).toBeCloseTo(eye[2]);
  });
});

describe('partColorHex', () => {
  it("packs the render's own r/g/b", () => {
    expect(partColorHex({ ...FIT_3005, part_color: [157, 157, 157] })).toBe(0x9d9d9d);
  });

  it("is null with no colour to impose, leaving the LDraw file's own", () => {
    expect(partColorHex(FIT_3005)).toBeNull();
    expect(partColorHex(null)).toBeNull();
  });
});

describe('threeStyle', () => {
  it('reads the CLI flags that have a three.js counterpart', () => {
    expect(threeStyle({ opacity: 0.55, line_width: 3, svg_bg: '#ffffff' }))
      .toEqual({ opacity: 0.55, lineWidth: 3, background: '#ffffff' });
  });

  it("treats the CLI's `none` background as transparent, not as a colour", () => {
    expect(threeStyle({ svg_bg: 'none' }).background).toBeNull();
    expect(threeStyle({ svg_bg: '' }).background).toBeNull();
  });

  it('falls back for a flag left unset, which the lab carries as null', () => {
    expect(threeStyle({ opacity: null, line_width: null }))
      .toEqual({ opacity: 1, lineWidth: 2, background: null });
  });

  it('clamps an opacity the settings panel let through', () => {
    expect(threeStyle({ opacity: 4 }).opacity).toBe(1);
    expect(threeStyle({ opacity: -1 }).opacity).toBe(0);
  });
});
