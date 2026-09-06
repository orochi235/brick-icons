import { afterEach, expect, it, vi } from 'vitest';
import { DEFAULT_PALETTE, readPalette } from '@lab/corpus/palette';

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
