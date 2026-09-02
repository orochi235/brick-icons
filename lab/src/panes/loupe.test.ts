import { describe, expect, it } from 'vitest';
import { HOME, MAX_ZOOM } from '@lab/panes/camera';
import {
  DEFAULT_FACTOR, MAX_FACTOR, MIN_FACTOR,
  bubbleDiameter, clampFactor, loupeCamera, loupeCameraForImage, showsLoupe,
  stageOffset,
} from '@lab/panes/loupe';
import { SOURCES } from '@lab/panes/sources';

describe('clampFactor', () => {
  it('holds the factor inside the range the wheel can reach', () => {
    expect(clampFactor(1)).toBe(MIN_FACTOR);
    expect(clampFactor(999)).toBe(MAX_FACTOR);
    expect(clampFactor(6)).toBe(6);
  });

  it('falls back rather than propagating a NaN into the transform', () => {
    expect(clampFactor(Number.NaN)).toBe(DEFAULT_FACTOR);
  });
});

describe('loupeCamera', () => {
  it('keeps the point under the cursor under the cursor', () => {
    const at = { x: 100, y: 50 };
    const next = loupeCamera(HOME, 4, at);
    // world point under `at` before == world point under `at` after
    const before = (at.x - HOME.pan.x) / HOME.zoom;
    const after = (at.x - next.pan.x) / next.zoom;
    expect(after).toBeCloseTo(before);
  });

  it('magnifies past the shared camera ceiling', () => {
    const zoomed = { zoom: MAX_ZOOM, pan: { x: 0, y: 0 } };
    expect(loupeCamera(zoomed, 8, { x: 0, y: 0 }).zoom).toBe(MAX_ZOOM * 8);
  });

  it('multiplies the shared zoom rather than replacing it', () => {
    expect(loupeCamera({ zoom: 3, pan: { x: 0, y: 0 } }, 4, { x: 0, y: 0 }).zoom).toBe(12);
  });
});

describe('loupeCameraForImage', () => {
  it('magnifies by the factor alone, whatever the shared camera', () => {
    expect(loupeCameraForImage(4, { x: 0, y: 0 }).zoom).toBe(4);
  });

  it('keeps the point under the cursor under the cursor', () => {
    const next = loupeCameraForImage(4, { x: 100, y: 50 });
    expect(next.pan).toEqual({ x: -300, y: -150 });
  });
});

describe('bubbleDiameter', () => {
  it('is a fraction of the shorter side', () => {
    expect(bubbleDiameter({ width: 1000, height: 500 })).toBe(200);
  });

  it('clamps at both ends so it is neither a dot nor the whole pane', () => {
    expect(bubbleDiameter({ width: 100, height: 100 })).toBe(120);
    expect(bubbleDiameter({ width: 4000, height: 4000 })).toBe(320);
  });
});

describe('stageOffset', () => {
  it('puts the cursor point at the bubble centre', () => {
    expect(stageOffset({ x: 100, y: 40 }, 200)).toEqual({ x: 0, y: 60 });
  });
});

describe('showsLoupe', () => {
  it('draws on the pane under the cursor', () => {
    expect(showsLoupe(SOURCES.naive, SOURCES.naive, false)).toBe(true);
  });

  it('draws nowhere else by default', () => {
    expect(showsLoupe(SOURCES.occt, SOURCES.naive, false)).toBe(false);
  });

  it('mirrors to the panes that share the render fit', () => {
    expect(showsLoupe(SOURCES.occt, SOURCES.naive, true)).toBe(true);
    expect(showsLoupe(SOURCES.diff, SOURCES.naive, true)).toBe(true);
  });

  it('does not mirror to a pane framed differently', () => {
    // LDView is auto-cropped and the decal is a carrier, not a view of the
    // part, so one body coordinate is not one world point on either.
    expect(showsLoupe(SOURCES.reference, SOURCES.naive, true)).toBe(false);
    expect(showsLoupe(SOURCES.decal, SOURCES.naive, true)).toBe(false);
    expect(showsLoupe(SOURCES['3d'], SOURCES.naive, true)).toBe(false);
  });

  it('mirrors from a mirroring pane only', () => {
    expect(showsLoupe(SOURCES.naive, SOURCES.reference, true)).toBe(false);
  });

  it('still draws under the cursor on a pane that never mirrors', () => {
    expect(showsLoupe(SOURCES.reference, SOURCES.reference, true)).toBe(true);
  });

  it('draws nothing when the pointer is in no pane', () => {
    expect(showsLoupe(SOURCES.naive, null, true)).toBe(false);
  });
});
