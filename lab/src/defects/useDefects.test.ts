import { describe, expect, it } from 'vitest';
import { buildDefect } from '@lab/defects/useDefects';

describe('buildDefect', () => {
  const args = {
    part: '3941',
    engines: ['occt'],
    title: 'borehole rim not drawn',
    notes: '',
    mark: { x: 0.42, y: 0.55, w: 0.11, h: 0.09 },
    config: { angle: '30,25', shading: 'outline', shade_style: 'flat3' },
    existing: [] as string[],
    today: '2026-08-31',
  };

  it('builds a record the server will accept', () => {
    const got = buildDefect(args);
    expect(got.id).toBe('3941-occt-borehole-rim-not-drawn');
    expect(got.part).toBe('3941');
    expect(got.engines).toEqual(['occt']);
    expect(got.status).toBe('open');
    expect(got.mark).toEqual(args.mark);
    expect(got.filed).toBe('2026-08-31');
  });

  it('records only the parameters that move the mark', () => {
    expect(buildDefect(args).seen)
      .toEqual({ angle: '30,25', shading: 'outline', shade_style: 'flat3' });
  });

  it('avoids an id already in use', () => {
    expect(buildDefect({ ...args, existing: ['3941-occt-borehole-rim-not-drawn'] }).id)
      .toBe('3941-occt-borehole-rim-not-drawn-2');
  });

  it('keeps notes when given', () => {
    expect(buildDefect({ ...args, notes: 'only at 30,25' }).notes).toBe('only at 30,25');
  });

  it('refuses an untitled defect, which nothing could later find', () => {
    expect(() => buildDefect({ ...args, title: '   ' })).toThrow(/title/i);
  });
});
