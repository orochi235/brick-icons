import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { SchemaField } from '@lab/api/types';
import { PoseBar, quickOptions } from '@lab/chrome/PoseBar';

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

describe('the loupe buttons', () => {
  const bar = (config: Record<string, unknown>, setConfig = () => {}) =>
    render(<PoseBar angle="iso" config={config} fields={FIELDS} setConfig={setConfig} />);

  it('names the key, because a modifier alone is undiscoverable', () => {
    bar({});
    expect(screen.getByText('loupe').getAttribute('title')).toMatch(/Alt/);
  });

  it('reads as off until the loupe is made sticky', () => {
    bar({});
    expect(screen.getByText('loupe').getAttribute('aria-pressed')).toBe('false');
  });

  it('reads as on once the loupe is sticky', () => {
    bar({ loupe_sticky: true });
    expect(screen.getByText('loupe').getAttribute('aria-pressed')).toBe('true');
  });

  it('lights while Alt is held, without being sticky', () => {
    bar({});
    fireEvent.keyDown(window, { key: 'Alt' });
    expect(screen.getByText('loupe').getAttribute('aria-pressed')).toBe('true');
    fireEvent.keyUp(window, { key: 'Alt' });
    expect(screen.getByText('loupe').getAttribute('aria-pressed')).toBe('false');
  });

  it('makes the loupe sticky on a click', () => {
    const setConfig = vi.fn();
    bar({}, setConfig);
    fireEvent.click(screen.getByText('loupe'));
    expect(setConfig).toHaveBeenCalledWith('loupe_sticky', true);
  });

  it('toggles the all-panes reach', () => {
    const setConfig = vi.fn();
    bar({ loupe_all_panes: true }, setConfig);
    fireEvent.click(screen.getByText('all panes'));
    expect(setConfig).toHaveBeenCalledWith('loupe_all_panes', false);
  });
});
