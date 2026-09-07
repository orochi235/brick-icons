import { afterEach, expect, it, vi } from 'vitest';
import {
  CELL_STATES, DEFAULT_PALETTE, PARAM_CSS_VAR, STATE_LABEL, readPalette,
} from '@lab/corpus/palette';
import { STATES, cssVarTable, labelTable, paramKeys, stateKeys, styleTable }
  from '@lab/corpus/states';

function stubComputedStyle(values: Record<string, string>) {
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: (prop: string) => values[prop] ?? '',
  } as CSSStyleDeclaration);
}

afterEach(() => { vi.restoreAllMocks(); });

it('resolves a state from its own custom properties', () => {
  stubComputedStyle({
    '--corpus-cell-defect-fill': '#111111',
    '--corpus-cell-defect-border': '#222222',
  });
  const palette = readPalette(document.createElement('div'));
  expect(palette.defect).toEqual({ fill: '#111111', border: '#222222', weight: 'thick' });
});

it('falls back to the tuned default for every state when nothing is declared', () => {
  stubComputedStyle({});
  expect(readPalette(document.createElement('div'))).toEqual(DEFAULT_PALETTE);
});

it('falls back per-property rather than losing the whole state', () => {
  stubComputedStyle({ '--corpus-cell-timeout-fill': '#101010' });
  const palette = readPalette(document.createElement('div'));
  expect(palette.timeout).toEqual({
    fill: '#101010', border: DEFAULT_PALETTE.timeout.border, weight: 'thick',
  });
});

it('never reads a border property for the unknown state', () => {
  stubComputedStyle({ '--corpus-cell-unknown-fill': '#abcabc',
                       '--corpus-cell-unknown-border': '#ff0000' });
  const palette = readPalette(document.createElement('div'));
  expect(palette.unknown).toEqual({ fill: '#abcabc', border: null, weight: null });
});

it('iterates the states in the table\'s own order', () => {
  expect(CELL_STATES).toEqual(stateKeys());
});

it('takes every fill, border and weight from the table rather than a second copy', () => {
  const styles = styleTable();
  for (const state of CELL_STATES) {
    expect(DEFAULT_PALETTE[state]).toEqual(styles[state]);
  }
});

it('takes every legend name from the table', () => {
  expect(STATE_LABEL).toEqual(labelTable());
});

it('points each color param at the state property that carries it', () => {
  const vars = cssVarTable();
  const expected: Record<string, string> = { caretColor: '--corpus-caret-color' };
  for (const state of STATES) {
    const param = paramKeys(state);
    expected[param.fill] = vars[state.key].fill;
    if (param.border !== null) expected[param.border] = vars[state.key].border as string;
  }
  expect(PARAM_CSS_VAR).toEqual(expected);
});
