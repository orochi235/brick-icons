import { describe, expect, it } from 'vitest';
import { enginePaneState, type EngineRenders } from '@lab/panes/engineState';
import type { RenderResult } from '@lab/api/client';

const SIG = 'sig-now';
const OLD = 'sig-before';

function result(over: Partial<RenderResult> = {}): RenderResult {
  return {
    ok: true, cached: false, argv: [], command: '', key: 'k1',
    artifacts: [{ name: '3941.svg', bytes: 10 }], seconds: 1, error: null, ...over,
  };
}

const EMPTY: EngineRenders = { renders: {}, errors: {}, stamps: {} };

describe('enginePaneState', () => {
  it('is idle before anything has been asked for', () => {
    expect(enginePaneState('naive', EMPTY, {}, { signature: SIG, running: false }))
      .toEqual({ pane: { kind: 'idle' }, busy: false });
  });

  it('waits on its own render while the run is in flight', () => {
    expect(enginePaneState('naive', EMPTY, {}, { signature: SIG, running: true }).pane)
      .toEqual({ kind: 'running' });
  });

  it('shows the drawing once its markup has been fetched', () => {
    const state: EngineRenders = {
      renders: { naive: result() }, errors: {}, stamps: { naive: SIG },
    };
    expect(enginePaneState('naive', state, { naive: '<svg/>' },
                           { signature: SIG, running: false }))
      .toEqual({ pane: { kind: 'svg', markup: '<svg/>' }, busy: false });
  });

  // The render is done but the pane cannot draw yet: the job reports `done`
  // while useArtifactSvg is still fetching the file. Reading the job alone
  // would blank the pane in that window.
  it('is still waiting when the render landed but its markup has not', () => {
    const state: EngineRenders = {
      renders: { naive: result() }, errors: {}, stamps: { naive: SIG },
    };
    expect(enginePaneState('naive', state, {}, { signature: SIG, running: false }).pane)
      .toEqual({ kind: 'running' });
  });

  it('shows this pane\'s own failure', () => {
    const state: EngineRenders = {
      renders: { occt: result({ ok: false, error: 'TopologyException' }) },
      errors: { occt: 'TopologyException' }, stamps: { occt: SIG },
    };
    expect(enginePaneState('occt', state, {}, { signature: SIG, running: false }).pane)
      .toEqual({ kind: 'error', message: 'TopologyException' });
  });

  it('keeps the last drawing up, marked busy, while the next render runs', () => {
    const state: EngineRenders = {
      renders: { naive: result() }, errors: {}, stamps: { naive: OLD },
    };
    expect(enginePaneState('naive', state, { naive: '<svg/>' },
                           { signature: SIG, running: true }))
      .toEqual({ pane: { kind: 'svg', markup: '<svg/>' }, busy: true });
  });

  it('drops a failure the moment the config that caused it changes', () => {
    const state: EngineRenders = {
      renders: { occt: result({ ok: false, error: 'TopologyException' }) },
      errors: { occt: 'TopologyException' }, stamps: { occt: OLD },
    };
    expect(enginePaneState('occt', state, {}, { signature: SIG, running: true }).pane)
      .toEqual({ kind: 'running' });
  });

  it('reads only its own source, so a slow neighbour cannot hold it back', () => {
    const state: EngineRenders = {
      renders: { naive: result() }, errors: {}, stamps: { naive: SIG },
    };
    const naive = enginePaneState('naive', state, { naive: '<svg/>' },
                                  { signature: SIG, running: true });
    const occt = enginePaneState('occt', state, { naive: '<svg/>' },
                                 { signature: SIG, running: true });
    expect(naive.pane).toEqual({ kind: 'svg', markup: '<svg/>' });
    expect(occt.pane).toEqual({ kind: 'running' });
  });
});
