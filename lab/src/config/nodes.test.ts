import { describe, expect, it } from 'vitest';
import { buildSchema, defaultsFor, RENDER_KEYS } from '@lab/config/nodes';
import type { SchemaField } from '@lab/api/types';

const field = (over: Partial<SchemaField>): SchemaField => ({
  key: 'engine', flag: '--engine', type: 'str', choices: null,
  help: '', nargs: null, default: null, effective: null, ...over,
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

  it('leaves a choice unset when nothing resolved one', () => {
    // Not choices[0]: guessing would put the lab on a setting the CLI never
    // uses. Unset means labels.toml decides, which is what the CLI does.
    const d = defaultsFor([field({ key: 'engine', choices: ['naive', 'occt'] })]);
    expect(d.engine).toBeNull();
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


describe('defaultsFor and the effective value', () => {
  it('prefers what labels.toml resolved over argparse\'s None', () => {
    const d = defaultsFor([field({ key: 'render_px', type: 'int',
                                   default: null, effective: 2048 })]);
    expect(d.render_px).toBe(2048);
  });

  it('prefers the effective choice over the first one listed', () => {
    const d = defaultsFor([field({ key: 'dither',
                                   choices: ['threshold', 'floyd', 'atkinson'],
                                   effective: 'atkinson' })]);
    expect(d.dither).toBe('atkinson');
  });

  it('opens on the SVG outline combo, since a pane shows an SVG', () => {
    const d = defaultsFor([field({ key: 'fmt', choices: ['png', 'svg'],
                                   effective: 'png' })]);
    expect(d.fmt).toBe('svg');
    expect(d.shading).toBe('outline');
    expect(d.shade_style).toBe('flat3');
  });

  it('leaves a flag with no effective value unset rather than zero', () => {
    const d = defaultsFor([field({ key: 'part_color', type: 'str' })]);
    expect(d.part_color).toBeNull();
  });
});

describe('a non-switch flag resolved to false', () => {
  it('is left unset, not passed as the string "False"', () => {
    // --debug-colors takes 'cycle' | 'ramp' | 'ramp=N'; its Config value is a
    // bool when off. Passing it through is an argparse error that fails the
    // entire render.
    const d = defaultsFor([field({ key: 'debug_colors', type: 'str',
                                   effective: false as unknown as null })]);
    expect(d.debug_colors).toBeNull();
  });

  it('still keeps a real switch false', () => {
    const d = defaultsFor([field({ key: 'weld_corners', type: 'bool',
                                   effective: false as unknown as null })]);
    expect(d.weld_corners).toBe(false);
  });
});
