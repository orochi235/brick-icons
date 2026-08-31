import { describe, expect, it } from 'vitest';
import { buildSchema, defaultsFor, RENDER_KEYS } from '@lab/config/nodes';
import type { SchemaField } from '@lab/api/types';

const field = (over: Partial<SchemaField>): SchemaField => ({
  key: 'engine', flag: '--engine', type: 'str', choices: null,
  help: '', nargs: null, default: null, ...over,
});

/** `buildSchema` also adds the lab's own fields; these tests are about the
 *  CLI-derived ones. */
const cliKeys = (schema: Record<string, unknown>) =>
  Object.keys(schema).filter((k) => k !== 'layout' && k !== 'sources');

describe('buildSchema', () => {
  it('turns a choices field into an enum node', () => {
    const s = buildSchema([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(s).toHaveProperty('engine');
  });

  it('keeps only the CLI keys that change a render', () => {
    const s = buildSchema([
      field({ key: 'engine', choices: ['naive', 'occt'] }),
      field({ key: 'out', type: 'str' }),
      field({ key: 'debug_dir', type: 'str' }),
      field({ key: 'list_colors', type: 'bool' }),
    ]);
    expect(cliKeys(s)).toEqual(['engine']);
  });

  it('drops a multi-value flag, which has no single control', () => {
    const s = buildSchema([
      field({ key: 'engine', choices: ['naive', 'occt'] }),
      field({ key: 'label_mm', type: 'float', nargs: 2 }),
    ]);
    expect(cliKeys(s)).toEqual(['engine']);
  });

  it('includes the lab-only source and layout fields', () => {
    const s = buildSchema([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(s).toHaveProperty('layout');
    expect(s).toHaveProperty('sources');
  });
});

describe('defaultsFor', () => {
  it('takes a value from the field default when it has one', () => {
    const d = defaultsFor([field({ key: 'render_px', type: 'int', default: 900 })]);
    expect(d.render_px).toBe(900);
  });

  it('takes the first choice when the default is null', () => {
    const d = defaultsFor([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(d.engine).toBe('naive');
  });

  it('defaults a switch to false', () => {
    const d = defaultsFor([field({ key: 'weld_corners', type: 'bool' })]);
    expect(d.weld_corners).toBe(false);
  });

  it('carries the part and the lab-only fields', () => {
    const d = defaultsFor([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(d.part).toBe('');
    expect(d.layout).toBe('split');
    expect(d.sources).toContain('occt');
  });
});

describe('RENDER_KEYS', () => {
  it('excludes the plumbing flags', () => {
    for (const key of ['out', 'root', 'config', 'list', 'debug_dir', 'list_colors']) {
      expect(RENDER_KEYS.has(key)).toBe(false);
    }
  });
});

import { renderConfig } from '@lab/config/nodes';

describe('renderConfig', () => {
  it('drops the lab-only fields', () => {
    const got = renderConfig({ part: '3941', layout: 'split',
                               sources: ['occt'], engine: 'occt' });
    expect(got).toEqual({ engine: 'occt' });
  });

  it('drops nulls and empty strings so the config file still decides', () => {
    expect(renderConfig({ engine: 'occt', angle: null, part_color: '' }))
      .toEqual({ engine: 'occt' });
  });

  it('keeps a false switch, which is a real value', () => {
    expect(renderConfig({ weld_corners: false })).toEqual({ weld_corners: false });
  });
});
