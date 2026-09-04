import { describe, expect, it } from 'vitest';
import { paneSpec, type PaneDeps } from '@lab/panes/paneSpec';
import { SOURCES } from '@lab/panes/sources';

const DEPS: PaneDeps = {
  engines: { renders: {}, errors: {}, stamps: { naive: 'sig' } },
  markup: { naive: '<svg/>' },
  run: { signature: 'sig', running: false },
  reference: { kind: 'running' },
  decal: { pane: { kind: 'image', src: '/d.png' }, note: '2 decals' },
  diff: { pane: { kind: 'image', src: '/diff.png' }, note: '3 components' },
  three: { node: 'the orbit view' },
};

describe('paneSpec', () => {
  it('gives an engine pane its own render', () => {
    expect(paneSpec(SOURCES.naive, DEPS).state).toEqual({ kind: 'svg', markup: '<svg/>' });
  });

  it('leaves an engine pane whose render has not landed idle', () => {
    expect(paneSpec(SOURCES.occt, DEPS).state).toEqual({ kind: 'idle' });
  });

  it('carries the diff and decal captions as notes', () => {
    expect(paneSpec(SOURCES.diff, DEPS).note).toBe('3 components');
    expect(paneSpec(SOURCES.decal, DEPS).note).toBe('2 decals');
  });

  it('hands the reference and decal panes their own state', () => {
    expect(paneSpec(SOURCES.reference, DEPS).state).toEqual({ kind: 'running' });
    expect(paneSpec(SOURCES.decal, DEPS).state).toEqual({ kind: 'image', src: '/d.png' });
  });

  // A mark is a fraction of the render it was drawn on, so it means something
  // only on a pane drawing that render at the shared camera.
  it('marks the panes that draw the run under test', () => {
    expect(paneSpec(SOURCES.naive, DEPS).marks).toBe(true);
    expect(paneSpec(SOURCES.reference, DEPS).marks).toBe(false);
    expect(paneSpec(SOURCES['3d'], DEPS).marks).toBe(false);
  });

  // A defect names engines, and `diff` is not one, so a mark drawn there
  // could never be found again.
  it('does not mark the diff pane, which a defect cannot name', () => {
    expect(paneSpec(SOURCES.diff, DEPS).marks).toBe(false);
  });

  it('gives the 3D pane the orbit view and what it says about registering', () => {
    const spec = paneSpec(SOURCES['3d'],
                          { ...DEPS, three: { node: 'the orbit view', note: 'unregistered' } });
    expect(spec.overlay).toBe('the orbit view');
    expect(spec.note).toBe('unregistered');
  });

  it('puts every pane on the shared camera, the 3D one included', () => {
    for (const source of [SOURCES.naive, SOURCES.diff, SOURCES.reference,
                          SOURCES.decal, SOURCES['3d']]) {
      expect(paneSpec(source, DEPS).followsCamera).toBe(true);
    }
  });

  it('specs every source in the catalog', () => {
    for (const source of Object.values(SOURCES)) {
      expect(paneSpec(source, DEPS).state).toBeDefined();
    }
  });
});
