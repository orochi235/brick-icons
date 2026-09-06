import { afterEach, beforeEach, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { useParams } from '@lab/corpus/useParams';

const STORAGE_KEY = 'brick-icons-lab.corpus-params';

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '<div class="lk-root"></div>';
});

afterEach(() => { document.body.innerHTML = ''; });

it('starts from the tuned defaults with nothing stored', () => {
  const { result } = renderHook(() => useParams());
  expect(result.current.params).toEqual(DEFAULT_PARAMS);
});

it('persists a change so a fresh hook picks it up -- surviving a reload', () => {
  const { result } = renderHook(() => useParams());
  act(() => result.current.setParam('cell', 48));
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).cell).toBe(48);

  const { result: reloaded } = renderHook(() => useParams());
  expect(reloaded.current.params.cell).toBe(48);
});

it('resets every field back to its default, and persists the reset', () => {
  const { result } = renderHook(() => useParams());
  act(() => {
    result.current.setParam('cell', 48);
    result.current.setParam('unknownFill', '#123456');
  });
  act(() => result.current.reset());
  expect(result.current.params).toEqual(DEFAULT_PARAMS);
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!)).toEqual(DEFAULT_PARAMS);
});

it('tolerates a corrupt store by falling back to defaults', () => {
  localStorage.setItem(STORAGE_KEY, '{not json');
  const { result } = renderHook(() => useParams());
  expect(result.current.params).toEqual(DEFAULT_PARAMS);
});

it('writes a color param onto .lk-root as a CSS custom property', () => {
  const { result } = renderHook(() => useParams());
  act(() => result.current.setParam('timeoutBorder', '#abcdef'));
  const root = document.querySelector('.lk-root') as HTMLElement;
  expect(root.style.getPropertyValue('--corpus-cell-timeout-border')).toBe('#abcdef');
});

it('writes every color var on mount, so a reload restores a customized palette', () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...DEFAULT_PARAMS, caretColor: '#00ff00' }));
  renderHook(() => useParams());
  const root = document.querySelector('.lk-root') as HTMLElement;
  expect(root.style.getPropertyValue('--corpus-caret-color')).toBe('#00ff00');
});
