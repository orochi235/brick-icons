import { describe, expect, it } from 'vitest';
import { diffCaption, diffPair, diffWarning } from '@lab/panes/useDiff';
import type { RenderResult } from '@lab/api/client';

const render = (over: Partial<RenderResult> = {}): RenderResult => ({
  ok: true, cached: false, argv: [], command: '', key: 'k',
  artifacts: [{ name: '3941.svg', bytes: 1 }], seconds: 1, error: null, ...over,
});

describe('diffCaption', () => {
  it('leads with the component count, not the pixel total', () => {
    expect(diffCaption({ components: 3, sizes: [120, 40, 8], pixels: 168, url: '' }))
      .toBe('3 components · largest 120px · 168px total');
  });

  it('says identical when nothing differs', () => {
    expect(diffCaption({ components: 0, sizes: [], pixels: 0, url: '' }))
      .toBe('identical');
  });

  it('is singular for one component', () => {
    expect(diffCaption({ components: 1, sizes: [9], pixels: 9, url: '' }))
      .toMatch(/^1 component ·/);
  });

  it('is empty with no result', () => {
    expect(diffCaption(null)).toBe('');
  });
});

describe('diffPair', () => {
  it('pairs the two engine renders', () => {
    const got = diffPair({ naive: render({ key: 'a' }), occt: render({ key: 'b' }) });
    expect(got).toEqual({ aKey: 'a', aName: '3941.svg', bKey: 'b', bName: '3941.svg' });
  });

  it('is null until both engines have rendered', () => {
    expect(diffPair({ naive: render() })).toBeNull();
  });

  it('is null when either render failed', () => {
    expect(diffPair({ naive: render(), occt: render({ ok: false }) })).toBeNull();
  });

  it('is null when a render wrote no SVG', () => {
    expect(diffPair({ naive: render(), occt: render({ artifacts: [] }) })).toBeNull();
  });

  it('always puts naive first, so the answer does not depend on arrival order', () => {
    const a = diffPair({ naive: render({ key: 'n' }), occt: render({ key: 'o' }) });
    const b = diffPair({ occt: render({ key: 'o' }), naive: render({ key: 'n' }) });
    expect(a).toEqual(b);
  });
});

describe('diffWarning', () => {
  it('warns while a fill style is on, because occt draws no fills', () => {
    expect(diffWarning({ shade_style: 'flat3' })).toMatch(/fill: none/);
  });

  it('is silent on strokes only, where the diff is the hidden-line work', () => {
    expect(diffWarning({ shade_style: 'none' })).toBeNull();
  });
});
