import { describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type { LabClient } from '@lab/api/client';
import { decalCaption, decalState, useDecal } from '@lab/panes/useDecal';

describe('decalState', () => {
  it('is idle without a part', () => {
    expect(decalState({ part: '', urls: [], error: null, loading: false }))
      .toEqual({ kind: 'idle' });
  });

  it('is running while extraction is in flight', () => {
    expect(decalState({ part: '3005p01', urls: [], error: null, loading: true }))
      .toEqual({ kind: 'running' });
  });

  it('shows the first decal, which is the largest print', () => {
    expect(decalState({ part: '3005p01', urls: ['/a.svg', '/b.svg'],
                        error: null, loading: false }))
      .toEqual({ kind: 'image', src: '/a.svg' });
  });

  // Running the extractor is what settles whether a part is printed, so an
  // empty result is an answer rather than a failure.
  it('says a part carries no decal rather than erroring', () => {
    expect(decalState({ part: '3005', urls: [], error: null, loading: false }))
      .toEqual({ kind: 'error', message: 'no decal on this part' });
  });

  it('reports a real failure as itself', () => {
    expect(decalState({ part: 'nope', urls: [], loading: false,
                        error: 'FileNotFoundError: nope' }))
      .toEqual({ kind: 'error', message: 'FileNotFoundError: nope' });
  });
});

describe('decalCaption', () => {
  it('says nothing for a single decal', () => {
    expect(decalCaption(['/a.svg'])).toBe('');
  });

  it('counts the surfaces it is not showing', () => {
    expect(decalCaption(['/a.svg', '/b.svg', '/c.svg'])).toBe('+2 more surfaces');
  });

  it('says nothing when there are none', () => {
    expect(decalCaption([])).toBe('');
  });
});

describe('useDecal gating', () => {
  it('does not run the extractor when the decal pane is off', async () => {
    const client = { decal: vi.fn(async () => ({ urls: [], names: [], cached: false })) };
    renderHook(() => useDecal(client as unknown as LabClient, '3005p01', false));
    await waitFor(() => expect(client.decal).not.toHaveBeenCalled());
  });

  it('runs it once the pane is on', async () => {
    const client = { decal: vi.fn(async () => ({ urls: [], names: [], cached: false })) };
    renderHook(() => useDecal(client as unknown as LabClient, '3005p01', true));
    await waitFor(() => expect(client.decal).toHaveBeenCalled());
  });
});
