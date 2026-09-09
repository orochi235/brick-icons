import { useState } from 'react';
import type { CacheReport } from '@lab/corpus/cacheReport';
import '@lab/corpus/CacheFailureButton.css';

export interface CacheFailureButtonProps {
  /** Gathers the report. Async because it probes a real render URL. */
  report: () => Promise<CacheReport>;
  /** Puts both upper rungs back to a cold start. Called AFTER the report is
   *  built, since it destroys the evidence the report is made of. */
  reset: () => void;
}

/** Says what happened to the wall's image ladder, then tries to unstick it.
 *
 *  One button and not two: by the time anyone reaches for this the wall has
 *  already been showing blurry cells for a while, and asking them to press
 *  "diagnose" and then "fix" in the right order is a way to lose the
 *  diagnosis. The order here is fixed -- report, then reset.
 */
export function CacheFailureButton({ report, reset }: CacheFailureButtonProps) {
  const [state, setState] = useState<{ report: CacheReport; copied: boolean }
                                     | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const got = await report();
      const json = JSON.stringify(got, null, 2);
      // The console copy is the one that always lands: the clipboard needs a
      // permission and a focused document, and this is worth having when
      // neither holds.
      console.warn('[corpus] cache failure report\n' + json);
      let copied = false;
      try {
        await navigator.clipboard.writeText(json);
        copied = true;
      } catch { /* console has it */ }
      setState({ report: got, copied });
      reset();
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="corpus-cachefail">
      <button type="button" className="corpus-action" disabled={busy}
              onClick={() => { void run(); }}>
        {busy ? 'Checking…' : 'Cache failure'}
      </button>
      {state && (
        <div className="corpus-cachefail__out" role="status">
          <p className="corpus-cachefail__head">
            {state.report.ladder.rung} rung at{' '}
            {state.report.camera.cellPx.toFixed(0)}px cells
            {' · '}
            {state.copied ? 'JSON copied' : 'JSON in the console'}
            {' · caches reset'}
          </p>
          <ul>
            {state.report.findings.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <button type="button" className="corpus-cachefail__close"
                  onClick={() => setState(null)}>Dismiss</button>
        </div>
      )}
    </span>
  );
}
