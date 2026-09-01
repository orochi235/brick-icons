import { describe, expect, it, vi } from 'vitest';
import type { JobState, LabClient } from '@lab/api/client';
import { jobStates, settledJob } from '@lab/api/jobPoll';

function state(kind: JobState['state'], results: unknown[] = []): JobState {
  return { id: 'j1', kind: 'render', state: kind, total: 1, done: 1,
           failed: 0, events: [], results } as unknown as JobState;
}

/** A client that walks the given states, one per poll, repeating the last. */
function client(states: JobState[]) {
  const job = vi.fn(async () => states[Math.min(job.mock.calls.length - 1,
                                                states.length - 1)]!);
  return { job } as unknown as LabClient & { job: typeof job };
}

describe('jobStates', () => {
  it('yields each state up to the one that is not running', async () => {
    const api = client([state('running'), state('running'), state('done')]);
    const seen = [];
    for await (const s of jobStates(api, 'j1', { pollMs: 0 })) seen.push(s.state);
    expect(seen).toEqual(['running', 'running', 'done']);
  });

  it('stops polling once the signal aborts', async () => {
    const api = client([state('running')]);
    const abort = new AbortController();
    const seen = [];
    for await (const s of jobStates(api, 'j1', { pollMs: 0, signal: abort.signal })) {
      seen.push(s.state);
      if (seen.length === 2) abort.abort();
    }
    expect(seen).toEqual(['running', 'running']);
    expect(api.job).toHaveBeenCalledTimes(2);
  });
});

describe('settledJob', () => {
  it('answers with the state the job settled in', async () => {
    const api = client([state('running'), state('done', ['r'])]);
    expect((await settledJob(api, 'j1', { pollMs: 0 }))?.results).toEqual(['r']);
  });

  it('answers null when the wait was abandoned, not the last state seen', async () => {
    const api = client([state('running')]);
    const abort = new AbortController();
    setTimeout(() => abort.abort(), 0);
    expect(await settledJob(api, 'j1', { pollMs: 1, signal: abort.signal })).toBeNull();
  });

  it('never polls a job it was told to abandon first', async () => {
    const api = client([state('done')]);
    const abort = new AbortController();
    abort.abort();
    expect(await settledJob(api, 'j1', { signal: abort.signal })).toBeNull();
    expect(api.job).not.toHaveBeenCalled();
  });
});
