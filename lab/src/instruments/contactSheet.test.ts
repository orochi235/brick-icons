import { describe, expect, it } from 'vitest';
import { createContactSheet } from '@lab/instruments/contactSheet';
import type { LabClient } from '@lab/api/client';
import type { SchemaField } from '@lab/api/types';

const FIELDS: SchemaField[] = [
  { key: 'engine', flag: '--engine', type: 'str', choices: ['naive', 'occt'],
    help: '', nargs: null, default: null, effective: 'naive' },
  { key: 'shading', flag: '--shading', type: 'str',
    choices: ['normal', 'cel', 'outline'], help: '', nargs: null,
    default: null, effective: 'normal' },
];

const LISTS = [
  { name: 'specimens', source: 'specimens.txt', parts: ['3001', '3941'] },
  { name: 'parts', source: 'parts.txt', parts: ['3001'] },
];

const client = {} as LabClient;

describe('createContactSheet', () => {
  it('is named for the workspace', () => {
    expect(createContactSheet(FIELDS, LISTS, client).name).toBe('contact-sheet');
  });

  it('opens on the first list', () => {
    expect(createContactSheet(FIELDS, LISTS, client).defaultConfig().list)
      .toBe('specimens');
  });

  it('takes its render flags from the CLI schema', () => {
    const config = createContactSheet(FIELDS, LISTS, client).defaultConfig();
    expect(config.engine).toBe('naive');
  });

  it('starts with no cells', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    expect(instrument.initialState(instrument.defaultConfig()).cells).toEqual([]);
  });

  it('re-runs when the list changes', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    const base = instrument.defaultConfig();
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, list: 'parts' }, state));
  });

  it('re-runs when a render flag changes', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    const base = instrument.defaultConfig();
    const state = instrument.initialState(base);
    expect(instrument.job!.key!(base, state))
      .not.toEqual(instrument.job!.key!({ ...base, engine: 'occt' }, state));
  });

  it('appends each cell as it arrives, keeping order', () => {
    const instrument = createContactSheet(FIELDS, LISTS, client);
    let state = instrument.initialState(instrument.defaultConfig());
    state = instrument.job!.onItem(
      { part: '3001', key: 'k1', svg: '3001.svg', error: null, seconds: 1 }, state);
    state = instrument.job!.onItem(
      { part: '3941', key: 'k2', svg: '3941.svg', error: null, seconds: 2 }, state);
    expect(state.cells.map((c: { part: string }) => c.part)).toEqual(['3001', '3941']);
  });

  it('does not start on its own, since a list is many renders', () => {
    expect(createContactSheet(FIELDS, LISTS, client).job!.auto).toBe(false);
  });
});
