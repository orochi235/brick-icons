import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GoldenStatus, summarizeGoldens } from '@lab/chrome/GoldenStatus';
import type { LabClient } from '@lab/api/client';

describe('summarizeGoldens', () => {
  it('says goldens match when they all do', () => {
    expect(summarizeGoldens([{ state: 'match' }, { state: 'match' }]))
      .toBe('goldens: match (2)');
  });

  it('leads with what moved, which is the thing worth acting on', () => {
    expect(summarizeGoldens([{ state: 'match' }, { state: 'moved' }]))
      .toBe('goldens: 1 moved of 2');
  });

  it('counts a case that was never frozen separately from a failure', () => {
    expect(summarizeGoldens([{ state: 'unfrozen' }])).toBe('goldens: 1 unfrozen');
  });

  it('reports a missing render as missing, not as a move', () => {
    expect(summarizeGoldens([{ state: 'missing' }])).toBe('goldens: 1 missing');
  });

  it('says a part has no cases rather than implying it passed', () => {
    expect(summarizeGoldens([])).toBe('goldens: no cases');
  });
});

describe('GoldenStatus', () => {
  const client = (results: { state: string }[]) => ({
    checkGoldens: vi.fn(async () => ({ job: 'j1', count: results.length })),
    job: vi.fn(async () => ({
      id: 'j1', kind: 'goldens', state: 'done' as const, total: results.length,
      done: results.length, failed: 0, events: [], results,
    })),
  } as unknown as LabClient);

  it('does not check until asked, because a check re-renders', () => {
    const api = client([]);
    render(<GoldenStatus client={api} part="3941" />);
    expect(api.checkGoldens).not.toHaveBeenCalled();
  });

  it('reports the result after a check', async () => {
    render(<GoldenStatus client={client([{ state: 'match' }])} part="3941" />);
    fireEvent.click(screen.getByText(/check goldens/i));
    await waitFor(() => expect(screen.getByText(/goldens: match/)).toBeTruthy());
  });

  it('offers nothing to check without a part', () => {
    render(<GoldenStatus client={client([])} part="" />);
    expect(screen.queryByText(/check goldens/i)).toBeNull();
  });
});
