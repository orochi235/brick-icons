import { afterEach, expect, it, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import type { ChangedEvent } from '@lab/api/types';
import { CHANGED_BATCH_MS, useChanged } from '@lab/api/useChanged';

afterEach(() => vi.useRealTimers());

const event = (part: string): ChangedEvent =>
  ({ part, source: 'occt', sha: `${part}-sha`, build: '9.c' });

function source() {
  let tell: (e: ChangedEvent) => void = () => {};
  const stop = vi.fn();
  const client = { onChanged: vi.fn((f: (e: ChangedEvent) => void) => { tell = f; return stop; }) };
  return { client, stop, tell: (e: ChangedEvent) => tell(e) };
}

it('hands a burst of events over as one batch', () => {
  vi.useFakeTimers();
  const { client, tell } = source();
  const batches: ChangedEvent[][] = [];
  renderHook(() => useChanged(client, (b) => batches.push(b)));
  tell(event('3001'));
  tell(event('3002'));
  vi.advanceTimersByTime(CHANGED_BATCH_MS - 1);
  expect(batches).toEqual([]);
  tell(event('3003'));
  vi.advanceTimersByTime(1);
  expect(batches.map((b) => b.map((e) => e.part))).toEqual([['3001', '3002', '3003']]);
});

it('does not let a steady stream hold a batch back', () => {
  vi.useFakeTimers();
  const { client, tell } = source();
  const batches: ChangedEvent[][] = [];
  renderHook(() => useChanged(client, (b) => batches.push(b)));
  for (let i = 0; i < 10; i++) {
    tell(event(`p${i}`));
    vi.advanceTimersByTime(CHANGED_BATCH_MS / 2);
  }
  expect(batches.length).toBeGreaterThanOrEqual(4);
});

it('stops listening and drops a pending batch on unmount', () => {
  vi.useFakeTimers();
  const { client, stop, tell } = source();
  const batches: ChangedEvent[][] = [];
  const { unmount } = renderHook(() => useChanged(client, (b) => batches.push(b)));
  tell(event('3001'));
  unmount();
  vi.advanceTimersByTime(CHANGED_BATCH_MS);
  expect(stop).toHaveBeenCalled();
  expect(batches).toEqual([]);
});

it('is quiet for a client that cannot listen', () => {
  expect(() => renderHook(() => useChanged({}, () => {}))).not.toThrow();
});
