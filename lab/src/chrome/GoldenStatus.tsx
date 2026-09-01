import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { settledJob } from '@lab/api/jobPoll';

export interface CaseResult {
  state: string;
}

export function summarizeGoldens(results: CaseResult[]): string {
  if (results.length === 0) return 'goldens: no cases';
  const count = (state: string) => results.filter((r) => r.state === state).length;
  const moved = count('moved');
  if (moved > 0) return `goldens: ${moved} moved of ${results.length}`;
  const missing = count('missing');
  if (missing > 0) return `goldens: ${missing} missing`;
  const unfrozen = count('unfrozen');
  if (unfrozen > 0) return `goldens: ${unfrozen} unfrozen`;
  return `goldens: match (${results.length})`;
}

/** A check re-renders the part once per combo, so it is a button, not a
 *  subscription: nothing fires it on a config change. */
export function GoldenStatus({ client, part }: { client: LabClient; part: string }) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const check = useRef<AbortController | null>(null);

  // A verdict belongs to the part it was checked for, so leaving that part
  // both stops the poll and drops what it said.
  useEffect(() => {
    setText('');
    return () => check.current?.abort();
  }, [part]);

  if (!part.trim()) return null;

  async function run() {
    check.current?.abort();
    const { signal } = (check.current = new AbortController());
    setBusy(true);
    setText('checking…');
    try {
      const started = await client.checkGoldens(part);
      const state = await settledJob(client, started.job, { signal });
      if (state) setText(summarizeGoldens(state.results as unknown as CaseResult[]));
    } catch (e) {
      if (!signal.aborted) setText(`goldens: ${(e as Error).message}`);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  return (
    <span className="golden-status">
      {text ? <span>{text}</span> : null}
      <button type="button" disabled={busy} onClick={() => void run()}>
        check goldens
      </button>
    </span>
  );
}
