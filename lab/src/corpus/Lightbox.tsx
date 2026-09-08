import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { LabClient } from '@lab/api/client';
import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { CATALOGS } from '@lab/corpus/catalogs';
import { Fingerprint } from '@lab/corpus/Fingerprint';
import { Tags, yearRange } from '@lab/corpus/tags';
import { defectId, engineFor } from '@lab/corpus/flag';
import { cellState } from '@lab/corpus/paint';
import type { CellState } from '@lab/corpus/palette';
import { cssVarTable } from '@lab/corpus/states';
import type { PartDetail } from '@lab/corpus/types';
import { STATUSES, type DefectStatus } from '@lab/defects/useDefects';
import { STATUS_BADGES } from '@lab/defects/statusBadges';
import '@lab/corpus/Lightbox.css';

function renderSrc(partId: string, slot: { source: string; sha256: string }) {
  return `/api/corpus/render/${slot.source}/${partId}.svg?v=${slot.sha256.slice(0, 8)}`;
}

/** The state the wall would color this slot's cell. An API older than the
 *  state fields sends none, and every slot here has a render, so the honest
 *  answer for a slot that says nothing is the ground a clean one gets. */
function slotState(slot: PartDetail['slots'][number],
                   part: PartDetail['part']): CellState {
  return cellState({
    out_of_scope: part.out_of_scope ?? false,
    open_defects: slot.open_defects ?? 0,
    review_defects: slot.review_defects ?? 0,
    error: slot.error ?? null,
    accepted_defects: slot.accepted_defects ?? 0,
    elsewhere: slot.elsewhere ?? [],
  });
}

const STATE_VAR = cssVarTable();

/** The CSS variable holding a state's border color, as a `var()` reference
 *  for `--slot-ground`. Naming the property rather than resolving it keeps a
 *  live color tweak reaching the lightbox, and keeps this table out of the
 *  stylesheet where a new state would have to be remembered twice. */
function groundVar(state: CellState): string | undefined {
  const prop = STATE_VAR[state]?.border;
  return prop ? `var(${prop})` : undefined;
}

/** Whether this defect is asking for a look at `source`: it was judged once
 *  against a render, and the slot draws something else now. Mirrors
 *  `defects.wants_review` on the server, which is what colors the cell. */
export function wantsReview(defect: PartDetail['defects'][number],
                            source: string, sha: string | undefined): boolean {
  if (defect.status !== 'open' || !sha) return false;
  const seen = defect.checked?.[source];
  return seen !== undefined && seen !== sha;
}

/** A defect's status where it is read rather than set: the same badge shape
 *  the tag row uses, so the two read as one kind of thing. A status the page
 *  does not know stays a word. */
function DefectStatusBadge({ status }: { status: string }) {
  const badge = STATUS_BADGES[status];
  if (!badge) return <em>{status}</em>;
  // The badge is aria-hidden, so the word it sets needs a text twin.
  return (
    <>
      <BadgeSwatch badge={badge} label={status} box={17} />
      <span className="corpus-visually-hidden">{status}</span>
    </>
  );
}

export function Lightbox({ partId, source, client, onClose }: {
  partId: string;
  source: string;
  client: LabClient;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PartDetail | null>(null);
  // The slot this view is *about* -- which render is marked, and which engine
  // a flag names. Seeded from the wall and free to differ from it, so a
  // comparison can be made here without disturbing the wall behind.
  const [shown, setShown] = useState(source);
  const [flagging, setFlagging] = useState(false);
  const [title, setTitle] = useState('');
  const [flagError, setFlagError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    void client.corpusPart(partId).then((d) => { if (live) setDetail(d); });
    return () => { live = false; };
  }, [partId, client]);

  useEffect(() => { setShown(source); }, [source]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => { closeRef.current?.focus(); }, []);

  // An API older than this component sends no slots -- the lab's server is a
  // long-lived process and outlives a reload of the page in front of it.
  const slots = detail?.slots ?? [];

  const file = async () => {
    setFlagError(null);
    try {
      await client.addDefect({
        id: defectId(partId, title),
        part: partId,
        engines: [engineFor(shown)],
        status: 'open',
        title: title.trim(),
        // Stamped with what you are looking at: this is the drawing the
        // defect describes, and the one a later render is compared against.
        ...(shaOf(shown) ? { checked: { [shown]: shaOf(shown) } } : {}),
        filed: new Date().toISOString().slice(0, 10),
      });
      setTitle('');
      setFlagging(false);
      setDetail(await client.corpusPart(partId));
    } catch (e) {
      setFlagError(e instanceof Error ? e.message : String(e));
    }
  };
  const shaOf = (source: string) =>
    slots.find((slot) => slot.source === source)?.sha256;

  /** Close a defect out, or send it back round. Either way the render in
   *  front of you is stamped as judged, so a defect left open stops asking
   *  until the slot draws something else again -- without that, one look at a
   *  redrawn fault would leave it shouting for good. */
  const verdict = async (id: string, status: DefectStatus) => {
    const sha = shaOf(shown);
    await client.patchDefect(id, {
      status,
      ...(sha ? { checked: { ...(detail?.defects.find((d) => d.id === id)?.checked ?? {}),
                             [shown]: sha } } : {}),
    });
    setDetail(await client.corpusPart(partId));
  };

  const years = detail
    ? yearRange(detail.part.year_from, detail.part.year_to,
                (detail.part.tags ?? []).includes('retired'))
    : null;

  // Portaled to the theme root rather than left inside the workspace: as a
  // child of the wall it drew under the shell's header, and a panel with the
  // slot and filter controls above it reads as part of the same view.
  const host = typeof document === 'undefined'
    ? null : document.querySelector('.lk-root') ?? document.body;

  const panel = (
    <div className="corpus-lightbox-scrim" role="presentation" onClick={onClose}>
    <div className="corpus-lightbox" role="dialog" aria-modal="true"
         aria-label={`Part ${partId}`} onClick={(e) => e.stopPropagation()}>
      <button type="button" className="corpus-close" aria-label="Close"
              ref={closeRef} onClick={onClose}>x</button>
      {!detail ? <p>loading {partId}…</p> : (
        <>
          <h2>{detail.part.title}</h2>
          <p className="corpus-sub">
            {detail.part.id} · {detail.part.category ?? 'uncategorised'} ·
            {' '}{detail.part.status}
            {detail.part.status_note ? ` · ${detail.part.status_note}` : ''}
            {years ? ` · ${years}` : ''}
            {detail.part.sets != null ? ` · ${detail.part.sets} sets` : ''}
          </p>
          <Tags tags={detail.part.tags ?? []} />
          {/* A radio group rather than a hand-built control: it carries the
              role, the name and the arrow-key roving for free, and the `<li>`
              stays a list item with neither a role nor a handler on it. */}
          <ul className="corpus-slots" role="radiogroup" aria-label="Slot shown">
            {slots.map((slot) => (
              <li key={slot.source} className="corpus-slot"
                  data-current={slot.source === shown}
                  data-state={slotState(slot, detail.part)}
                  data-ground={groundVar(slotState(slot, detail.part)) ? '' : undefined}
                  ref={(el) => {
                    const ground = groundVar(slotState(slot, detail.part));
                    if (ground) el?.style.setProperty('--slot-ground', ground);
                  }}
                  data-retired={(detail.part.tags ?? []).includes('retired')}>
                {/* Capture, and stopped there: React derives a radio's onChange
                    from the same click, so a bubble-phase handler cannot keep
                    the shift-click from also picking the slot. */}
                <label className="corpus-slot-pick" title="Shift-click to open this render in a new tab"
                       onClickCapture={(e) => {
                         if (!e.shiftKey) return;
                         e.preventDefault();
                         e.stopPropagation();
                         window.open(renderSrc(detail.part.id, slot), '_blank', 'noopener');
                       }}>
                  <input type="radio" name="corpus-slot-shown" aria-label={slot.source}
                         className="corpus-slot-radio" checked={slot.source === shown}
                         onChange={() => setShown(slot.source)} />
                  <img className="corpus-big" alt={`${detail.part.id} drawn by ${slot.source}`}
                       src={renderSrc(detail.part.id, slot)} />
                  <span className="corpus-slot-name">{slot.source}</span>
                </label>
              </li>
            ))}
            {slots.length === 0 && <li>no slot has drawn this part</li>}
          </ul>
          <div className="corpus-actions">
            <a className="corpus-action" href={`/index.html?part=${encodeURIComponent(partId)}`}
               target="_blank" rel="noopener noreferrer">Open in lab</a>
            <button type="button"
                    className={flagging ? 'corpus-action' : 'corpus-action corpus-action-flag'}
                    onClick={() => setFlagging((was) => !was)}>
              {flagging ? 'Cancel' : 'Flag a problem'}
            </button>
          </div>
          {flagging && (
            <form className="corpus-flag" onSubmit={(e) => { e.preventDefault(); void file(); }}>
              <label>
                What is wrong
                <input value={title} autoFocus
                       onChange={(e) => setTitle(e.target.value)}
                       placeholder="the near rim is drawn as a whole circle" />
              </label>
              <button type="submit" disabled={!title.trim()}>File against {shown}</button>
              {flagError && <span className="corpus-flag-error" role="alert">{flagError}</span>}
            </form>
          )}
          <ul className="corpus-catalogs">
            {CATALOGS.map((catalog) => (
              <li key={catalog.name}>
                <a href={catalog.url(detail.part.id)} target="_blank" rel="noopener noreferrer">
                  {catalog.name}
                </a>
              </li>
            ))}
          </ul>
          <h3>Built from</h3>
          <Fingerprint features={detail.features} />
          <h3>Measurements</h3>
          <table>
            <thead>
              <tr><th>engine</th><th>extra d99</th><th>missing px</th>
                  <th>secs</th><th>error</th></tr>
            </thead>
            <tbody>
              {detail.findings.map((f) => (
                <tr key={f.engine}>
                  <td>{f.engine}</td>
                  <td>{f.extra_d99 ?? '—'}</td>
                  <td>{f.missing_px ?? '—'}</td>
                  <td>{f.secs ?? '—'}</td>
                  <td>{f.error ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>Defects</h3>
          {detail.defects.length === 0 ? <p>none</p> : (
            <ul>
              {detail.defects.map((d) => {
                const asks = wantsReview(d, shown, shaOf(shown));
                return (
                  <li key={d.id} className="corpus-defect" data-review={asks || undefined}>
                    <span>{d.title}</span>
                    <DefectStatusBadge status={d.status} />
                    {asks && (
                      <span className="corpus-verdict">
                        <button type="button" onClick={() => void verdict(d.id, 'fixed')}>
                          fixed
                        </button>
                        <button type="button" onClick={() => void verdict(d.id, 'open')}>
                          still broken
                        </button>
                      </span>
                    )}
                    <select aria-label={`status of ${d.title}`} value={d.status}
                            onChange={(e) => void verdict(
                              d.id, e.target.value as DefectStatus)}>
                      {STATUSES.map((st) => <option key={st} value={st}>{st}</option>)}
                    </select>
                  </li>
                );
              })}
            </ul>
          )}
          <h3>Runs</h3>
          <ul>
            {detail.runs.map((r) => (
              <li key={`${r.id}-${r.engine}`}>
                {r.started.slice(0, 10)} · {r.kind} · {r.commit_sha.slice(0, 7)}
                {' '}· {r.engine} · d99 {r.extra_d99 ?? '—'}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
    </div>
  );

  return host ? createPortal(panel, host) : panel;
}
