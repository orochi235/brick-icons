import { describe, expect, it } from 'vitest';
import { SOURCES, enabledSources, sourceConfig } from '@lab/panes/sources';

describe('SOURCES', () => {
  it('declares naive and occt as engine sources', () => {
    expect(SOURCES.naive.kind).toBe('engine');
    expect(SOURCES.occt.kind).toBe('engine');
  });

  it('labels every source', () => {
    for (const source of Object.values(SOURCES)) expect(source.label).toBeTruthy();
  });
});

describe('enabledSources', () => {
  it('returns the declared sources in declaration order', () => {
    expect(enabledSources(['occt', 'naive']).map((s) => s.id))
      .toEqual(['naive', 'occt']);
  });

  it('ignores an unknown id rather than throwing', () => {
    expect(enabledSources(['naive', 'nope'] as never).map((s) => s.id))
      .toEqual(['naive']);
  });

  it('is empty for an empty selection', () => {
    expect(enabledSources([])).toEqual([]);
  });
});

describe('sourceConfig', () => {
  it('pins the engine for an engine source', () => {
    expect(sourceConfig(SOURCES.occt, { engine: 'naive', shading: 'outline' }))
      .toEqual({ engine: 'occt', shading: 'outline' });
  });

  it('leaves a non-engine source config alone', () => {
    const base = { engine: 'naive' };
    expect(sourceConfig(SOURCES['3d'], base)).toEqual(base);
  });
});
