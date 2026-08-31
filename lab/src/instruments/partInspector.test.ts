import { describe, expect, it, vi } from 'vitest';
import { createPartInspector } from '@lab/instruments/partInspector';
import { setPendingPart } from '@lab/config/pending';
import type { LabClient } from '@lab/api/client';
import type { SchemaField } from '@lab/api/types';

const FIELDS: SchemaField[] = [
  { key: 'engine', flag: '--engine', type: 'str', choices: ['naive', 'occt'],
    help: '', nargs: null, default: null },
  { key: 'shading', flag: '--shading', type: 'str',
    choices: ['normal', 'cel', 'outline'], help: '', nargs: null, default: null },
];

const client = {} as LabClient;

describe('createPartInspector', () => {
  it('is named for the workspace', () => {
    expect(createPartInspector(FIELDS, client).name).toBe('part-inspector');
  });

  it('opens on the pending part', () => {
    setPendingPart('3941');
    expect(createPartInspector(FIELDS, client).defaultConfig().part).toBe('3941');
  });

  it('opens empty when nothing is pending', () => {
    expect(createPartInspector(FIELDS, client).defaultConfig().part).toBe('');
  });

  it('takes its config keys from the schema it was given', () => {
    const config = createPartInspector(FIELDS, client).defaultConfig();
    expect(config.engine).toBe('naive');
    expect(config.shading).toBe('normal');
  });

  it('declares the sources as layers', () => {
    const ids = createPartInspector(FIELDS, client).layers?.ids ?? [];
    expect(ids).toContain('naive');
    expect(ids).toContain('occt');
  });

  it('re-runs the job when the part changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const before = instrument.job!.key!({ ...instrument.defaultConfig(), part: '3941' }, state);
    const after = instrument.job!.key!({ ...instrument.defaultConfig(), part: '4070' }, state);
    expect(before).not.toEqual(after);
  });

  it('re-runs the job when a render flag changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const base = { ...instrument.defaultConfig(), part: '3941' };
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, shading: 'outline' }, state));
  });

  it('does not re-run the job when only the layout changes', () => {
    const instrument = createPartInspector(FIELDS, client);
    const base = { ...instrument.defaultConfig(), part: '3941' };
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .toEqual(instrument.job!.key!({ ...base, layout: 'stack' }, state));
  });

  it('records a failed render as the pane\'s error', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', result: { ok: false, cached: false, argv: [], command: '',
        key: '', artifacts: [], seconds: 0, error: 'TopologyException' } },
      state);
    expect(next.errors.occt).toBe('TopologyException');
  });

  it('folds a finished render into state under its source', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', result: { ok: true, cached: false, argv: [], command: '',
        key: 'k1', artifacts: [{ name: '3941.svg', bytes: 1 }], seconds: 2,
        error: null } },
      state);
    expect(next.renders.occt?.key).toBe('k1');
  });

  it('contributes the command line to the chrome', () => {
    const ids = (createPartInspector(FIELDS, client).chrome ?? []).map((c) => c.id);
    expect(ids).toContain('command-line');
  });

  it('starts the job automatically', () => {
    expect(createPartInspector(FIELDS, client).job!.auto).toBe(true);
  });
});
