import { useState } from 'react';
import type { LabClient } from '@lab/api/client';

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

  if (!part.trim()) return null;

  async function check() {
    setBusy(true);
    setText('checking…');
    try {
      const started = await client.checkGoldens(part);
      let state = await client.job(started.job);
      while (state.state === 'running') {
        await new Promise((r) => setTimeout(r, 250));
        state = await client.job(started.job);
      }
      setText(summarizeGoldens(state.results as unknown as CaseResult[]));
    } catch (e) {
      setText(`goldens: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="golden-status">
      {text ? <span>{text}</span> : null}
      <button type="button" disabled={busy} onClick={() => void check()}>
        check goldens
      </button>
    </span>
  );
}
