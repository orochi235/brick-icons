import { describe, expect, it } from 'vitest';
import type { SchemaField } from '@lab/api/types';
import { quickOptions } from '@lab/chrome/PoseBar';

function field(key: string, choices: string[] | null): SchemaField {
  return { key, flag: `--${key}`, type: 'str', choices, help: '',
           nargs: null, default: null, effective: null };
}

const FIELDS = [
  field('engine', ['naive', 'occt', 'cadquery']),
  field('shading', ['outline', 'cel', 'normal']),
  field('shade_style', ['flat3', 'none']),
  field('part_color', null),
];

describe('quickOptions', () => {
  it('takes its values from the CLI choices', () => {
    const engine = quickOptions(FIELDS).find((o) => o.key === 'engine');
    expect(engine?.values).toEqual(['naive', 'occt', 'cadquery']);
  });

  it('names the lab-only layout values itself', () => {
    const layout = quickOptions(FIELDS).find((o) => o.key === 'layout');
    expect(layout?.values).toEqual(['grid', 'split', 'stack']);
  });

  it('drops a control whose flag the CLI no longer offers', () => {
    const keys = quickOptions([field('engine', ['naive'])]).map((o) => o.key);
    expect(keys).toEqual(['engine', 'layout']);
  });
});
