import { describe, expect, it, vi } from 'vitest';
import { createPartInspector } from '@lab/instruments/partInspector';
import { setPendingPart } from '@lab/config/pending';
import type { LabClient } from '@lab/api/client';
import type { SchemaField } from '@lab/api/types';

const FIELDS: SchemaField[] = [
  { key: 'engine', flag: '--engine', type: 'str', choices: ['naive', 'occt'],
    help: '', nargs: null, default: null, effective: 'naive' },
  { key: 'shading', flag: '--shading', type: 'str',
    choices: ['normal', 'cel', 'outline'], help: '', nargs: null,
    default: null, effective: 'normal' },
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
    // The lab's opening combo overrides the CLI default here: a pane shows an
    // SVG, and `--shading normal` produces none. See OPENING_COMBO.
    expect(config.shading).toBe('outline');
  });

  // Not `layers`: labkit's layer capability writes labkit's own state, not the
  // instrument's config, so the toggles it drew were inert. The panes are
  // driven by `config.sources`, which PoseBar writes.
  it('opens with the two engine panes enabled', () => {
    const config = createPartInspector(FIELDS, client).defaultConfig();
    expect(config.sources).toEqual(['naive', 'occt']);
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
      .not.toEqual(instrument.job!.key!({ ...base, shading: 'cel' }, state));
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
      { source: 'occt', signature: 'sig',
        result: { ok: false, cached: false, argv: [], command: '',
                  key: '', artifacts: [], seconds: 0, error: 'TopologyException' } },
      state);
    expect(next.errors.occt).toBe('TopologyException');
  });

  it('folds a finished render into state under its source', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', signature: 'sig',
        result: { ok: true, cached: false, argv: [], command: '',
                  key: 'k1', artifacts: [{ name: '3941.svg', bytes: 1 }], seconds: 2,
                  error: null } },
      state);
    expect(next.renders.occt?.key).toBe('k1');
  });

  it('stamps a render with the run it came from, so a pane can spot a stale one', () => {
    const instrument = createPartInspector(FIELDS, client);
    const state = instrument.initialState(instrument.defaultConfig());
    const next = instrument.job!.onItem(
      { source: 'occt', signature: 'sig',
        result: { ok: true, cached: false, argv: [], command: '', key: 'k1',
                  artifacts: [], seconds: 2, error: null } },
      state);
    expect(next.stamps.occt).toBe('sig');
  });

  it('contributes the command line to the chrome', () => {
    const ids = (createPartInspector(FIELDS, client).chrome ?? []).map((c) => c.id);
    expect(ids).toContain('command-line');
  });

  it('starts the job automatically', () => {
    expect(createPartInspector(FIELDS, client).job!.auto).toBe(true);
  });
});
