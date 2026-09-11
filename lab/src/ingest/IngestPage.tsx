import { useCallback, useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { LabSwitcher } from '@weasel-js/labkit';
import { PAGES } from '@lab/nav/pages';
import { changeOf, outcomeOf } from '@lab/ingest/change';
import type { IngestAttempts, IngestRun } from '@lab/ingest/types';
import '@lab/ingest/ingest.css';

/** The states a run's tally can carry, in the order they are worth reading:
 *  what it took in, then what it did not. Anything the server reports that is
 *  not listed here still shows, after these -- a new state in `attempts`
 *  appears on the page without being named twice. */
const STATE_ORDER = ['stored', 'cached', 'present', 'none', 'error'];

function orderedCounts(counts: Record<string, number>): [string, number][] {
  const known = STATE_ORDER.filter((k) => k in counts).map(
    (k) => [k, counts[k]!] as [string, number]);
  const rest = Object.entries(counts).filter(([k]) => !STATE_ORDER.includes(k));
  return [...known, ...rest];
}

/** `330` -> `5m 30s`. Runs here go from under a second to several hours, and
 *  a bare second count stops being readable somewhere in the middle. */
export function duration(secs: number | null): string {
  if (secs === null) return 'open';
  if (secs < 60) return `${secs.toFixed(secs < 10 ? 1 : 0)}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ${Math.round(secs % 60)}s`;
  return `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

/** The local time of an ISO timestamp, date dropped when it is today's: a log
 *  read the day it was written is scanned by clock time. */
export function when(iso: string, now = new Date()): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const time = at.toLocaleTimeString(undefined,
    { hour: '2-digit', minute: '2-digit' });
  return at.toDateString() === now.toDateString()
    ? time
    : `${at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${time}`;
}

function Args({ args }: { args: Record<string, unknown> }) {
  const entries = Object.entries(args);
  if (entries.length === 0) return null;
  return (
    <span className="ingest-args">
      {entries.map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
        .join(' ')}
    </span>
  );
}

function Detail({ view, failedOnly, onFailedOnly }: {
  view: IngestAttempts | null;
  failedOnly: boolean;
  onFailedOnly: (next: boolean) => void;
}) {
  if (view === null) return <p className="ingest-detail-empty">reading…</p>;
  if (view.total === 0) {
    return (
      <p className="ingest-detail-empty">
        This run took nothing in.
      </p>
    );
  }
  return (
    <div className="ingest-detail">
      {view.errors.length > 0 && (
        <ul className="ingest-errors">
          {view.errors.map((e) => (
            <li key={e.error}>
              <strong>{e.error}</strong> {e.n.toLocaleString()}
            </li>
          ))}
        </ul>
      )}
      <label className="ingest-failed-only">
        <input type="checkbox" checked={failedOnly}
               onChange={(e) => onFailedOnly(e.target.checked)} />
        failures only
      </label>
      <table className="ingest-attempts">
        <thead>
          <tr><th>part</th><th>slot</th><th>was</th><th>state</th><th>secs</th>
            <th>error</th></tr>
        </thead>
        <tbody>
          {view.rows.map((row) => (
            /* Colored by whether the row moved the part, which is the whole
               reason to read a list where most rows repeat last run. */
            <tr key={`${row.part_id}/${row.source}`}
                data-change={changeOf(row.prior, outcomeOf(row)) ?? undefined}>
              <td>{row.part_id}</td>
              <td>{row.source}</td>
              {/* Null means this run met the part first, which is a fact
                  about it rather than a missing value: say so once here
                  instead of leaving the reader to read a dash as either. */}
              <td className="ingest-prior">{row.prior ?? 'never tried'}</td>
              <td>{row.state ?? '—'}</td>
              <td>{row.secs === null ? '' : row.secs.toFixed(1)}</td>
              <td title={row.detail ?? undefined}>{row.error ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {view.rows.length < view.total && (
        <p className="ingest-capped">
          {view.rows.length.toLocaleString()} of {view.total.toLocaleString()}{' '}
          shown
        </p>
      )}
    </div>
  );
}

/** Which ingests have run, and what each one took in. Read-only: this is the
 *  record of what reached the database, not a way to start anything. */
export function IngestPage({ client }: { client: LabClient }) {
  const [runs, setRuns] = useState<IngestRun[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [failedOnly, setFailedOnly] = useState(false);
  const [detail, setDetail] = useState<IngestAttempts | null>(null);

  useEffect(() => {
    let live = true;
    client.ingestRuns()
      .then((rows) => { if (live) setRuns(rows); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [client]);

  useEffect(() => {
    if (open === null) return;
    let live = true;
    setDetail(null);
    client.ingestAttempts(open, failedOnly)
      .then((view) => { if (live) setDetail(view); })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [client, open, failedOnly]);

  const toggle = useCallback((id: number) => {
    setOpen((prev) => (prev === id ? null : id));
    setFailedOnly(false);
  }, []);

  return (
    <main className="ingest-page">
      <header className="ingest-head">
        <LabSwitcher title="Ingestion log" pages={PAGES} />
      </header>
      {error !== null && <p className="ingest-error">{error}</p>}
      {runs !== null && runs.length === 0 && <p>Nothing has been ingested yet.</p>}
      <ul className="ingest-runs">
        {(runs ?? []).map((run) => (
          <li key={run.id}>
            <div className="ingest-run" role="button" tabIndex={0}
                 aria-expanded={open === run.id}
                 aria-label={`run ${run.id}, ${run.kind}`}
                 onClick={() => toggle(run.id)}
                 onKeyDown={(e) => {
                   if (e.key === 'Enter' || e.key === ' ') {
                     e.preventDefault();
                     toggle(run.id);
                   }
                 }}>
              <span className="ingest-kind">{run.kind}</span>
              <span className="ingest-when">{when(run.started)}</span>
              <span className="ingest-secs">{duration(run.secs)}</span>
              <span className="ingest-counts">
                {orderedCounts(run.counts).map(([state, n]) => (
                  <span key={state} className="ingest-count" data-state={state}>
                    {n.toLocaleString()} {state}
                  </span>
                ))}
              </span>
              <code className="ingest-commit">{run.commit_sha}</code>
              <Args args={run.args} />
            </div>
            {open === run.id && (
              <Detail view={detail} failedOnly={failedOnly}
                      onFailedOnly={setFailedOnly} />
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
