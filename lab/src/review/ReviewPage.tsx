import { useCallback, useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { LabSwitcher } from '@weasel-js/labkit';
import { PAGES } from '@lab/nav/pages';
import { CHIP, MaterialBar } from '@lab/shared/MaterialBar';
import { when } from '@lab/ingest/IngestPage';
import type { ReviewEntry, ReviewList, ReviewSide, ReviewView, Verdict }
  from '@lab/review/types';
import '@lab/review/review.css';

/** The verdicts and the key that presses each, in the order the buttons sit. */
export const VERDICT_KEYS: [Verdict, string][] = [
  ['fixed', 'f'], ['better', 'b'], ['neutral', 'n'], ['regression', 'r'],
];

const fixed = (v: number | null | undefined, places: number) =>
  v === null || v === undefined ? '' : v.toFixed(places);

/** One row of the before/after table: label, and the two cells' text. */
type Row = [label: string, before: string, after: string];

export function rowsFor(before: ReviewSide, after: ReviewSide): Row[] {
  const edge = (s: ReviewSide) => s.edge && s.edge.declared_len !== null
    ? `${fixed(s.edge.missing_len, 1)} of ${fixed(s.edge.declared_len, 1)}`
    : '';
  return [
    ['build', before.build ?? '', after.build ?? ''],
    ['made', before.made_at ? when(before.made_at) : '',
             after.made_at ? when(after.made_at) : ''],
    ['run', before.run_id === null ? '' : String(before.run_id),
            after.run_id === null ? '' : String(after.run_id)],
    ['secs', fixed(before.secs, 1), fixed(after.secs, 1)],
    ['d99', fixed(before.extra_d99, 2), fixed(after.extra_d99, 2)],
    ['missing px', before.missing_px?.toLocaleString() ?? '',
                   after.missing_px?.toLocaleString() ?? ''],
    ['edge gap', edge(before), edge(after)],
    ['error', before.error ?? '', after.error ?? ''],
  ].filter(([, b, a]) => b !== '' || a !== '') as Row[];
}

function Panel({ src, label, alt, onLoad, onError }: {
  src: string; label: React.ReactNode; alt: string;
  onLoad?: () => void; onError?: () => void;
}) {
  return (
    <figure className="review-panel">
      <img src={src} alt={alt} loading="lazy" onLoad={onLoad} onError={onError} />
      <figcaption>{label}</figcaption>
    </figure>
  );
}

/** LDView's drawing of the same part: what before and after cannot say,
 *  which is which of them is right. Absent on a checkout with no LDView,
 *  and the card carries on without it. */
function ReferencePanel({ src, part, angle }: {
  src: string; part: string; angle: string;
}) {
  const [missing, setMissing] = useState(false);
  const label = <>reference · {angle}</>;
  if (missing) {
    return (
      <figure className="review-panel review-panel-missing">
        <div className="review-no-reference">no reference render</div>
        <figcaption>{label}</figcaption>
      </figure>
    );
  }
  return (
    <Panel src={src} label={label} alt={`${part} reference`}
           onError={() => setMissing(true)} />
  );
}

function Card({ entry, focused, referenceAngle, onFocus, onVerdict, onUndo,
                onMeasured }: {
  entry: ReviewEntry;
  focused: boolean;
  referenceAngle: string;
  onFocus: () => void;
  onVerdict: (verdict: Verdict, note: string) => void;
  onUndo: () => void;
  onMeasured: () => void;
}) {
  const [note, setNote] = useState('');
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView?.({ block: 'nearest' });
  }, [focused]);

  const diffLabel = entry.diff
    ? <>diff · {entry.diff.components.toLocaleString()} components · {entry.diff.pixels.toLocaleString()} px</>
    : <>diff · measuring…</>;

  return (
    <article className="review-card" id={entry.id} ref={ref}
             data-focused={focused || undefined}
             data-verdict={entry.judged?.verdict}
             onFocus={onFocus} onClick={onFocus} tabIndex={-1}
             aria-label={`${entry.part} in ${entry.source}`}>
      <header className="review-card-head">
        <a className="review-part" href={`/index?part=${encodeURIComponent(entry.part)}`}>
          {entry.part}
        </a>
        <span className="review-title">{entry.title}</span>
        <span className="material-chip-label review-slot">
          <MaterialBar source={entry.source} {...CHIP} />{entry.source}
        </span>
        <span className="review-by">{entry.by}</span>
        <time className="review-when" dateTime={entry.at}>{when(entry.at)}</time>
      </header>

      {entry.superseded_by && (
        <p className="review-superseded">
          The slot has drawn this part again since:{' '}
          <a href={`#${entry.superseded_by}`}>newer entry</a>.
        </p>
      )}

      <div className="review-panels">
        <ReferencePanel src={entry.urls.reference} part={entry.part}
                        angle={referenceAngle} />
        <Panel src={entry.urls.before} label="before" alt={`${entry.part} before`} />
        <Panel src={entry.urls.after} label="after" alt={`${entry.part} after`} />
        <Panel src={entry.urls.diff} label={diffLabel} alt={`${entry.part} diff`}
               onLoad={entry.diff ? undefined : onMeasured} />
      </div>

      <div className="review-facts">
        <table className="review-numbers">
          <thead>
            <tr><th scope="col" aria-label="measure" /><th scope="col">before</th><th scope="col">after</th></tr>
          </thead>
          <tbody>
            {rowsFor(entry.before, entry.after).map(([label, b, a]) => (
              <tr key={label} data-changed={b !== a || undefined}>
                <th scope="row">{label}</th>
                <td>{b}</td>
                <td>{a}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="review-links">
          {entry.defects.length > 0 && (
            <ul className="review-defects">
              {entry.defects.map((d) => (
                <li key={d.id} data-status={d.status}>
                  <span className="review-defect-status">{d.status}</span>{' '}
                  <span className="review-defect-title">{d.title}</span>
                  <span className="review-defect-id">{d.id}</span>
                  <span className="review-defect-checked">
                    {d.checked === null ? 'never judged in this slot'
                      : d.checked === entry.before.sha256 ? 'judged against before'
                      : d.checked === entry.after.sha256 ? 'judged against after'
                      : 'judged against an older render'}
                  </span>
                </li>
              ))}
            </ul>
          )}
          {entry.request && (
            <p className="review-request">
              redraw asked by {entry.request.by} {when(entry.request.at)}
            </p>
          )}
          {entry.defects.length === 0 && !entry.request && (
            <p className="review-unlinked">no open defect or request on this slot</p>
          )}
        </div>
      </div>

      {entry.judged ? (
        <p className="review-judged">
          <strong>{entry.judged.verdict}</strong>
          {entry.judged.note && <span className="review-note">{entry.judged.note}</span>}
          <time dateTime={entry.judged.at}>{when(entry.judged.at)}</time>
          <button type="button" className="review-undo" onClick={onUndo}>
            undo <kbd>u</kbd>
          </button>
        </p>
      ) : (
        <div className="review-verdicts">
          <textarea className="review-note-input" placeholder="note"
                    aria-label={`note for ${entry.part}`} value={note}
                    rows={1} onChange={(e) => setNote(e.target.value)} />
          {VERDICT_KEYS.map(([verdict, key]) => (
            <button key={verdict} type="button" data-verdict={verdict}
                    onClick={() => onVerdict(verdict, note)}>
              {verdict} <kbd>{key}</kbd>
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

/** Renders that displaced an older one, waiting to be judged. */
export function ReviewPage({ client }: { client: LabClient }) {
  const [view, setView] = useState<ReviewView>('linked');
  const [minComponents, setMinComponents] = useState(1);
  const [showJudged, setShowJudged] = useState(false);
  const [list, setList] = useState<ReviewList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState(0);
  const [measuring, setMeasuring] = useState(false);

  const load = useCallback(() => {
    let live = true;
    client.review(view, minComponents, showJudged)
      .then((body) => { if (live) { setList(body); setError(null); } })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [client, view, minComponents, showJudged]);
  useEffect(load, [load]);

  const entries = list?.entries ?? [];

  const replace = useCallback((updated: ReviewEntry) => {
    setList((prev) => prev && {
      ...prev,
      entries: prev.entries.map((e) => (e.id === updated.id ? updated : e)),
    });
  }, []);

  // A card judged in this session keeps its place in the list instead of
  // vanishing, so `undo` is reachable without first ticking "show judged".
  // A reload drops them, which is what the filter is for.
  const judge = useCallback(async (entry: ReviewEntry, verdict: Verdict, note: string) => {
    try {
      replace(await client.judge(entry.id, verdict, note));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [client, replace]);

  const undo = useCallback(async (entry: ReviewEntry) => {
    try {
      const updated = await client.undoJudgement(entry.id);
      replace(updated);
      if (updated.restored === false) {
        setError(`${entry.part}: the verdict predates the undo record, so the `
          + 'defect is open again but its previous checked sha is gone.');
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [client, replace]);

  const refresh = useCallback((entry: ReviewEntry) => {
    client.reviewEntry(entry.id).then(replace).catch(() => {});
  }, [client, replace]);

  const measure = useCallback(async () => {
    setMeasuring(true);
    try {
      await client.measureReview(50);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMeasuring(false);
    }
  }, [client, load]);

  // Keys act on the focused card. Typing in the note or a control is typing,
  // not a verdict, so anything editable swallows them.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /^(TEXTAREA|INPUT|SELECT)$/.test(target.tagName)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'j') { setFocus((f) => Math.min(entries.length - 1, f + 1)); return; }
      if (e.key === 'k') { setFocus((f) => Math.max(0, f - 1)); return; }
      if (e.key === 'u') {
        const judged = entries[focus];
        if (judged?.judged) void undo(judged);
        return;
      }
      const hit = VERDICT_KEYS.find(([, key]) => key === e.key);
      const entry = entries[focus];
      if (hit && entry && !entry.judged) {
        const note = document.querySelector<HTMLTextAreaElement>(
          `[id="${entry.id}"] .review-note-input`)?.value ?? '';
        void judge(entry, hit[0], note);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [entries, focus, judge, undo]);

  useEffect(() => {
    setFocus((f) => Math.min(f, Math.max(0, entries.length - 1)));
  }, [entries.length]);

  const unmeasured = entries.filter((e) => e.diff === null).length;
  const judgedHere = entries.filter((e) => e.judged !== null).length;

  return (
    <main className="lk-root review-page">
      <header className="review-head">
        <LabSwitcher title="Review" pages={PAGES} path="/review" />
        <div className="review-controls" role="group" aria-label="view">
          <button type="button" data-active={view === 'linked' || undefined}
                  onClick={() => setView('linked')}>Linked</button>
          <button type="button" data-active={view === 'all' || undefined}
                  onClick={() => setView('all')}>All changes</button>
          {view === 'all' && (
            <label className="review-min">
              at least
              <input type="number" min={0} value={minComponents}
                     aria-label="minimum components"
                     onChange={(e) => setMinComponents(Math.max(0, Number(e.target.value) || 0))} />
              components
            </label>
          )}
          <label className="review-show-judged">
            <input type="checkbox" checked={showJudged}
                   onChange={(e) => setShowJudged(e.target.checked)} />
            show judged
          </label>
          {view === 'all' && unmeasured > 0 && (
            <button type="button" className="review-measure" disabled={measuring}
                    onClick={() => void measure()}>
              {measuring ? 'measuring…' : `measure ${Math.min(50, unmeasured)} of ${unmeasured} unmeasured`}
            </button>
          )}
        </div>
        {list && (
          <p className="review-count">
            {entries.length.toLocaleString()} of {list.total.toLocaleString()} shown
            {judgedHere > 0 && <> · {judgedHere.toLocaleString()} judged</>}
          </p>
        )}
      </header>
      {error !== null && <p className="review-error">{error}</p>}
      {list !== null && entries.length === 0 && (
        <p className="review-empty">
          {view === 'linked'
            ? 'Nothing linked to an open defect or a redraw request is waiting.'
            : 'No replaced render clears the bar.'}
        </p>
      )}
      <div className="review-cards">
        {entries.map((entry, i) => (
          <Card key={entry.id} entry={entry} focused={i === focus}
                referenceAngle={list?.reference_angle ?? ''}
                onFocus={() => setFocus(i)}
                onVerdict={(verdict, note) => void judge(entry, verdict, note)}
                onUndo={() => void undo(entry)}
                onMeasured={() => refresh(entry)} />
        ))}
      </div>
    </main>
  );
}
