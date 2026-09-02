import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useLoupe } from '@lab/panes/useLoupe';

const alt = (type: 'keydown' | 'keyup') =>
  act(() => { window.dispatchEvent(new KeyboardEvent(type, { key: 'Alt' })); });

function setup(config: Record<string, unknown> = {}) {
  const setConfig = vi.fn();
  const hook = renderHook(() => useLoupe(config, setConfig));
  return { hook, setConfig };
}

describe('useLoupe', () => {
  it('is dead until Alt goes down', () => {
    const { hook } = setup();
    expect(hook.result.current.live).toBe(false);
    alt('keydown');
    expect(hook.result.current.live).toBe(true);
    alt('keyup');
    expect(hook.result.current.live).toBe(false);
  });

  it('stays up without the key when it is sticky', () => {
    const { hook } = setup({ loupe_sticky: true });
    expect(hook.result.current.live).toBe(true);
  });

  it('drops the key when the window loses focus', () => {
    const { hook } = setup();
    alt('keydown');
    act(() => { window.dispatchEvent(new Event('blur')); });
    expect(hook.result.current.live).toBe(false);
  });

  it('reports the hovered pane only while it is live', () => {
    const { hook } = setup();
    act(() => hook.result.current.onHover('naive', { x: 4, y: 5 }));
    expect(hook.result.current.over).toBeNull();
    alt('keydown');
    expect(hook.result.current.over).toBe('naive');
    expect(hook.result.current.at).toEqual({ x: 4, y: 5 });
  });

  it('forgets the pane when the pointer leaves it', () => {
    const { hook } = setup();
    alt('keydown');
    act(() => hook.result.current.onHover('naive', { x: 4, y: 5 }));
    act(() => hook.result.current.onHover('naive', null));
    expect(hook.result.current.over).toBeNull();
  });

  it('forgets where the pointer was when it goes dead', () => {
    const { hook } = setup();
    alt('keydown');
    act(() => hook.result.current.onHover('naive', { x: 4, y: 5 }));
    alt('keyup');
    alt('keydown');
    expect(hook.result.current.over).toBeNull();
  });

  it('reads the factor from the config, clamped', () => {
    expect(setup({ loupe_factor: 9 }).hook.result.current.factor).toBe(9);
    expect(setup({ loupe_factor: 500 }).hook.result.current.factor).toBe(16);
    expect(setup().hook.result.current.factor).toBe(6);
  });

  it('writes a bumped factor back to the config', () => {
    const { hook, setConfig } = setup({ loupe_factor: 6 });
    act(() => hook.result.current.bumpFactor(1));
    expect(setConfig).toHaveBeenCalledWith('loupe_factor', 7);
  });

  it('will not bump past the range', () => {
    const { hook, setConfig } = setup({ loupe_factor: 16 });
    act(() => hook.result.current.bumpFactor(1));
    expect(setConfig).toHaveBeenCalledWith('loupe_factor', 16);
  });

  it('passes the all-panes toggle through', () => {
    expect(setup({ loupe_all_panes: true }).hook.result.current.allPanes).toBe(true);
    expect(setup().hook.result.current.allPanes).toBe(false);
  });
});
