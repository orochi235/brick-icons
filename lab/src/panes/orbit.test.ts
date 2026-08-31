import { describe, expect, it } from 'vitest';
import { angleFromOrbit, orbitFromAngle, parseAngle, formatAngle } from '@lab/panes/orbit';

describe('parseAngle', () => {
  it('reads a lat,long pair', () => {
    expect(parseAngle('30,25')).toEqual({ lat: 30, long: 25 });
  });

  it('reads the named presets the CLI accepts', () => {
    expect(parseAngle('iso')).toEqual({ lat: 30, long: 45 });
    expect(parseAngle('top')).toEqual({ lat: 90, long: 0 });
    expect(parseAngle('bottom')).toEqual({ lat: -90, long: 0 });
    expect(parseAngle('left')).toEqual({ lat: 0, long: -90 });
  });

  it('tolerates spaces', () => {
    expect(parseAngle(' 30 , 25 ')).toEqual({ lat: 30, long: 25 });
  });

  it('is null for nonsense, so a caller can leave the angle alone', () => {
    expect(parseAngle('sideways')).toBeNull();
    expect(parseAngle('')).toBeNull();
  });
});

describe('formatAngle', () => {
  it('writes what the CLI parses', () => {
    expect(formatAngle({ lat: 30, long: 25 })).toBe('30,25');
  });

  it('rounds, because a drag produces fractions the CLI does not need', () => {
    expect(formatAngle({ lat: 30.4, long: 24.6 })).toBe('30,25');
  });

  it('normalizes longitude into -180..180', () => {
    expect(formatAngle({ lat: 0, long: 190 })).toBe('0,-170');
    expect(formatAngle({ lat: 0, long: -190 })).toBe('0,170');
  });

  it('clamps latitude to the poles', () => {
    expect(formatAngle({ lat: 120, long: 0 })).toBe('90,0');
  });
});

describe('orbitFromAngle', () => {
  it('puts the camera above the part for the top view', () => {
    const p = orbitFromAngle({ lat: 90, long: 0 }, 100);
    expect(p.y).toBeCloseTo(100);
    expect(p.x).toBeCloseTo(0);
    expect(p.z).toBeCloseTo(0);
  });

  it('puts the camera in front for the front view', () => {
    const p = orbitFromAngle({ lat: 0, long: 0 }, 100);
    expect(p.z).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(0);
  });

  it('puts the camera to the right for the right view', () => {
    const p = orbitFromAngle({ lat: 0, long: 90 }, 100);
    expect(p.x).toBeCloseTo(100);
    expect(p.z).toBeCloseTo(0);
  });

  it('keeps the radius', () => {
    const p = orbitFromAngle({ lat: 30, long: 45 }, 250);
    expect(Math.hypot(p.x, p.y, p.z)).toBeCloseTo(250);
  });
});

describe('angleFromOrbit', () => {
  it('inverts orbitFromAngle', () => {
    for (const angle of [{ lat: 30, long: 25 }, { lat: 0, long: 0 },
                         { lat: -45, long: 120 }, { lat: 60, long: -30 }]) {
      const back = angleFromOrbit(orbitFromAngle(angle, 100));
      expect(back.lat).toBeCloseTo(angle.lat);
      expect(back.long).toBeCloseTo(angle.long);
    }
  });

  it('is stable through a format round trip', () => {
    const text = formatAngle(angleFromOrbit(orbitFromAngle({ lat: 30, long: 45 }, 100)));
    expect(text).toBe('30,45');
  });
});
