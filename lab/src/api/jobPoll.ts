import type { JobState, LabClient } from '@lab/api/client';

export interface PollOptions {
  /** Aborting stops the polling. A caller that has gone away must pass one. */
  signal?: AbortSignal;
  /** Poll interval. Zero in tests; the app leaves it at the default. */
  pollMs?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Every state a job is seen in, ending with the first one that is not
 *  running. A caller that wants each batch of results as it lands reads them
 *  off the states; a caller that only wants the answer uses `settledJob`. */
export async function* jobStates(
  client: LabClient, id: string, { signal, pollMs = 250 }: PollOptions = {},
): AsyncIterable<JobState> {
  for (;;) {
    if (signal?.aborted) return;
    const state = await client.job(id);
    if (signal?.aborted) return;
    yield state;
    if (state.state !== 'running') return;
    await sleep(pollMs);
  }
}

/** The state a job settled in, or null if the wait was abandoned — so a
 *  caller cannot mistake an abort for an answer. */
export async function settledJob(
  client: LabClient, id: string, options: PollOptions = {},
): Promise<JobState | null> {
  let last: JobState | null = null;
  for await (const state of jobStates(client, id, options)) last = state;
  return last && last.state !== 'running' ? last : null;
}
