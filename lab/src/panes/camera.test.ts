import { describe, expect, it } from 'vitest';
import { HOME, cssTransform, panBy, readView, zoomAt } from '@lab/panes/camera';

describe('readView', () => {
  it('returns home for a view it does not recognise', () => {
    expect(readView(undefined)).toEqual(HOME);
    expect(readView({ orbit: 1 })).toEqual(HOME);
  });

  it('passes a well-formed view through', () => {
    const v = { zoom: 2, pan: { x: 10, y: -4 } };
    expect(readView(v)).toEqual(v);
  });

  it('rejects a non-finite zoom rather than propagating NaN', () => {
    expect(readView({ zoom: Number.NaN, pan: { x: 0, y: 0 } })).toEqual(HOME);
  });
});

describe('panBy', () => {
  it('adds the delta in screen pixels', () => {
    expect(panBy(HOME, 5, -3).pan).toEqual({ x: 5, y: -3 });
  });

  it('leaves zoom alone', () => {
    expect(panBy({ zoom: 3, pan: { x: 0, y: 0 } }, 1, 1).zoom).toBe(3);
  });
});

describe('zoomAt', () => {
  it('scales by the factor', () => {
    expect(zoomAt(HOME, 2, 0, 0).zoom).toBe(2);
  });

  it('keeps the cursor point fixed', () => {
    const next = zoomAt(HOME, 2, 100, 50);
    // the world point under (100,50) must still be under (100,50)
    expect(next.pan).toEqual({ x: -100, y: -50 });
  });

  it('clamps to the zoom range', () => {
    expect(zoomAt(HOME, 1000, 0, 0).zoom).toBe(64);
    expect(zoomAt(HOME, 0.0001, 0, 0).zoom).toBe(0.1);
  });

  it('composes: zooming in then out returns to home', () => {
    const there = zoomAt(HOME, 2, 40, 40);
    expect(zoomAt(there, 0.5, 40, 40)).toEqual(HOME);
  });
});

describe('cssTransform', () => {
  it('translates before it scales', () => {
    expect(cssTransform({ zoom: 2, pan: { x: 8, y: 4 } }))
      .toBe('translate(8px, 4px) scale(2)');
  });
});
