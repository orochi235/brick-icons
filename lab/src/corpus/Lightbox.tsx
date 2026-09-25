import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { LabClient } from '@lab/api/client';
import { settledJob } from '@lab/api/jobPoll';
import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { CATALOGS } from '@lab/corpus/catalogs';
import { Fingerprint } from '@lab/corpus/Fingerprint';
import { Measurements } from '@lab/corpus/Measurements';
import { poseNote } from '@lab/corpus/posed';
import { Lineage, Tags, TAG_BOX, yearRange } from '@lab/corpus/tags';
import { defectId, engineFor } from '@lab/corpus/flag';
import { ALL_BADGES, cellState } from '@lab/corpus/paint';
import type { CellState } from '@lab/corpus/palette';
import { cssVarTable } from '@lab/corpus/states';
import type { PartDetail } from '@lab/corpus/types';
import { ZoomView } from '@lab/corpus/ZoomView';
import { STATUSES, type DefectStatus } from '@lab/defects/useDefects';
import { STATUS_BADGES } from '@lab/defects/statusBadges';
import { CHIP, MaterialBar } from '@lab/shared/MaterialBar';
import { chartRank, materialOf } from '@lab/shared/materials';
import '@lab/corpus/Lightbox.css';

// Lazy, and the only import of it: three.js, the LDraw loader and drei are
// most of a megabyte, and the wall must not pay for them to draw a thumbnail.
const PartOrbit = lazy(() => import('@lab/corpus/PartOrbit'));

type Slot = PartDetail['slots'][number];

// Zero-width strokes only hide inside a translucent slot's own render --
// `materialOf` says which slots those are, so every other slot's src is
// untouched by the toggle.
function renderSrc(partId: string, slot: Slot, outlineTranslucent: boolean) {
  const outline = outlineTranslucent && materialOf(slot.source).finish === 'trans';
  const params = `v=${slot.sha256?.slice(0, 8)}${outline ? '&outline=1' : ''}`;
  return `/api/corpus/render/${slot.source}/${partId}.svg?${params}`;
}

/** What a slot with no render has to say for itself: the error that stopped
 *  it and how long it ran, or that nobody has run it. */
function whyNothing(slot: Slot): string[] {
  if (!slot.error) return ['not drawn'];
  return slot.secs != null ? [slot.error, `${slot.secs}s`] : [slot.error];
}

/** The state the wall would color this slot's cell. An API older than the
 *  state fields sends none, and the honest answer for a slot that says
 *  nothing is the ground a clean one gets. */
function slotState(slot: Slot, part: PartDetail['part']): CellState {
  return cellState({
    out_of_scope: part.out_of_scope ?? false,
    open_defects: slot.open_defects ?? 0,
    review_defects: slot.review_defects ?? 0,
    error: slot.error ?? null,
    accepted_defects: slot.accepted_defects ?? 0,
    elsewhere: slot.elsewhere ?? [],
  });
}

/** The badge the sub-line draws in place of a plain word, when one of its
 *  tokens -- in practice the category -- names one. Matched case-insensitively:
 *  `ALL_BADGES` keys are lowercase tags, `category` is titled for display. */
function tokenBadge(token: string | null) {
  return token ? ALL_BADGES[token.toLowerCase()] : undefined;
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
                            source: string,
                            sha: string | null | undefined): boolean {
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

export function Lightbox({ partId, source, client, onClose,
                          successor, predecessors, onPart }: {
  partId: string;
  source: string;
  client: LabClient;
  onClose: () => void;
  /** Both ends of the replacement link, from the cell the wall opened this
   *  from: the part detail the server sends carries neither. */
  successor?: string | null;
  predecessors?: string[];
  onPart?: (id: string) => void;
}) {
  const [detail, setDetail] = useState<PartDetail | null>(null);
  // The slot this view is *about* -- which render is marked, and which engine
  // a flag names. Seeded from the wall and free to differ from it, so a
  // comparison can be made here without disturbing the wall behind.
  const [shown, setShown] = useState(source);
  const [flagging, setFlagging] = useState(false);
  // On with the lightbox: the part is what somebody opened it to look at, and
  // a view behind a button is a view nobody turns. The chunk is still lazy, so
  // the wall pays for three.js when a lightbox opens and not to draw a
  // thumbnail; the button is there to put it away.
  const [turning, setTurning] = useState(true);
  const [outlineTranslucent, setOutlineTranslucent] = useState(false);
  const [title, setTitle] = useState('');
  const [flagError, setFlagError] = useState<string | null>(null);
  // Armed by one click and fired by the next: the button closes every
  // defect on the part at once, which is too much to hand to a slip.
  const [fixing, setFixing] = useState<'idle' | 'armed' | 'busy'>('idle');
  const [fixError, setFixError] = useState<string | null>(null);
  const [redraw, setRedraw] = useState<{ drawing: true } | { error: string } | null>(null);
  const [zoomedSlot, setZoomedSlot] = useState<Slot | null>(null);
  const gone = useRef(new AbortController());
  const closeRef = useRef<HTMLButtonElement>(null);
  // The radio a double-click opened the zoomed view from, so closing it can
  // hand focus back rather than dropping it to the document body.
  const zoomOpenerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let live = true;
    void client.corpusPart(partId).then((d) => { if (live) setDetail(d); });
    return () => { live = false; };
  }, [partId, client]);

  useEffect(() => { setShown(source); }, [source]);

  // One listener deciding both cases, rather than a second one on the zoomed
  // view racing it: closing the zoom first, when it is open, cannot depend on
  // which of two listeners on `window` ran first, because there is only one.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (zoomedSlot !== null) { setZoomedSlot(null); return; }
      onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, zoomedSlot]);

  useEffect(() => { closeRef.current?.focus(); }, []);

  // Only fires on the close transition: the ref stays null until a
  // double-click sets it, so mounting with no zoom open focuses nothing.
  useEffect(() => {
    if (zoomedSlot === null) zoomOpenerRef.current?.focus();
  }, [zoomedSlot]);

  useEffect(() => {
    const ctl = gone.current;
    return () => ctl.abort();
  }, []);

  // An API older than this component sends no slots -- the lab's server is a
  // long-lived process and outlives a reload of the page in front of it.
  //
  // The slot you arrived on survives the filter: opening a plain brick from
  // the decal wall and finding no decal slot disagrees with the wall behind.
  const slots = (detail?.slots ?? [])
    .filter((slot) => !slot.not_applicable || slot.source === shown)
    .sort((a, b) => chartRank(a.source) - chartRank(b.source));

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

  /** Draw the slot on screen again. The server decides whether that happens
   *  now or in the slot's next fleet round; either way the detail is reloaded,
   *  so the new drawing or the queued note is what shows. */
  const redrawShown = async () => {
    setRedraw({ drawing: true });
    try {
      const answer = await client.redraw(partId, shown);
      if (answer.local && answer.job) {
        const job = await settledJob(client, answer.job, { signal: gone.current.signal });
        if (!job) return;
        const failure = job.events.find((event) => !event.ok);
        setRedraw(failure ? { error: failure.message } : null);
      } else {
        setRedraw(null);
      }
      setDetail(await client.corpusPart(partId));
    } catch (e) {
      setRedraw({ error: e instanceof Error ? e.message : String(e) });
    }
  };
  const drawing = redraw !== null && 'drawing' in redraw;

  const unfixed = (detail?.defects ?? []).filter((d) => d.status !== 'fixed').length;
  const flagged = detail !== null && detail.part.status !== 'unreviewed';
  const markFixed = async () => {
    if (fixing === 'idle') { setFixing('armed'); return; }
    setFixing('busy');
    setFixError(null);
    try {
      setDetail(await client.markFixed(partId));
    } catch (e) {
      setFixError(e instanceof Error ? e.message : String(e));
    }
    setFixing('idle');
  };
  const fixLabel = fixing === 'busy' ? 'Marking…'
    : fixing === 'armed' ? (unfixed > 0 ? `Close ${unfixed} as fixed` : 'Clear status')
    : 'Mark fixed';
  const queuedAt = slots.find((slot) => slot.source === shown)?.requested_at;

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
  const pose = detail ? poseNote(detail.part.preview) : null;
  const categoryBadge = detail ? tokenBadge(detail.part.category) : undefined;
  // The badge stands in for the plain word above, so the same mark must not
  // also show in the tag row below it.
  const subTags = detail
    ? (detail.part.tags ?? []).filter((tag) =>
        !categoryBadge || tag.toLowerCase() !== detail.part.category!.toLowerCase())
    : [];

  // Portaled to the theme root rather than left inside the workspace: as a
  // child of the wall it drew under the shell's header, and a panel with the
  // slot and filter controls above it reads as part of the same view.
  const host = typeof document === 'undefined'
    ? null : document.querySelector('.lk-root') ?? document.body;

  const panel = (
    <>
    <div className="corpus-lightbox-scrim" role="presentation" onClick={onClose}>
    <div className="corpus-lightbox" role="dialog" aria-modal="true"
         aria-label={`Part ${partId}`} onClick={(e) => e.stopPropagation()}>
      <button type="button" className="corpus-close" aria-label="Close"
              ref={closeRef} onClick={onClose}>x</button>
      {/* The frame is up before the fetch is: a dialog that answers a click
          with a loading screen reads as slower than one that opens and fills
          in, and the id is a real heading rather than a placeholder for the
          title that replaces it. */}
      <div className="corpus-title-row">
        <h2>{detail?.part.title ?? partId}</h2>
        {years && <span className="corpus-years">{years}</span>}
      </div>
      {detail && (
        <>
          <p className="corpus-sub">
            {/* Opts into the panel's UI font, like the slot names below --
                the id is what the eye should land on, not the monospace body. */}
            <span className="corpus-id">{detail.part.id}</span> ·{' '}
            {categoryBadge ? (
              <>
                <BadgeSwatch badge={categoryBadge} label={detail.part.category!} box={TAG_BOX} />
                <span className="corpus-visually-hidden">{detail.part.category}</span>
              </>
            ) : (detail.part.category ?? 'uncategorised')} ·
            {' '}{detail.part.status}
            {detail.part.status_note ? ` · ${detail.part.status_note}` : ''}
            {detail.part.sets != null ? ` · ${detail.part.sets} sets` : ''}
          </p>
          <Tags tags={subTags} />
          <Lineage successor={successor ?? detail.part.successor}
                   predecessors={predecessors ?? detail.part.predecessors}
                   onPart={onPart} />
          {/* Every render below is drawn from the one global angle, so a part
              the library poses is one the drawings may be showing the wrong
              side of. */}
          {pose && (
            <p className="corpus-pose">LDraw poses this part: {pose}</p>
          )}
          {/* A radio group rather than a hand-built control: it carries the
              role, the name and the arrow-key roving for free, and the `<li>`
              stays a list item with neither a role nor a handler on it. */}
          <ul className="corpus-slots" role="radiogroup" aria-label="Slot shown">
            {slots.map((slot) => (
              <li key={slot.source} className="corpus-slot"
                  data-source={slot.source}
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
                <label className="corpus-slot-pick"
                       title={slot.sha256
                         ? 'Shift-click to open this render in a new tab' : undefined}
                       onClickCapture={(e) => {
                         if (!e.shiftKey || !slot.sha256) return;
                         e.preventDefault();
                         e.stopPropagation();
                         window.open(renderSrc(detail.part.id, slot, outlineTranslucent),
                                     '_blank', 'noopener');
                       }}
                       onDoubleClick={(e) => {
                         // The two clicks a dblclick follows already picked the
                         // slot; shift-click's own handler above sent it to a
                         // new tab instead, and this must stay out of its way.
                         if (e.shiftKey || !slot.sha256) return;
                         zoomOpenerRef.current = e.currentTarget.querySelector('input');
                         setZoomedSlot(slot);
                       }}>
                  <input type="radio" name="corpus-slot-shown" aria-label={slot.source}
                         className="corpus-slot-radio" checked={slot.source === shown}
                         onChange={() => setShown(slot.source)} />
                  {slot.sha256 ? (
                    <img className="corpus-big" alt={`${detail.part.id} drawn by ${slot.source}`}
                         src={renderSrc(detail.part.id, slot, outlineTranslucent)} />
                  ) : (
                    <span className="corpus-big corpus-slot-empty">
                      {whyNothing(slot).map((line) => <span key={line}>{line}</span>)}
                    </span>
                  )}
                  <span className="corpus-slot-name material-chip-label">
                    <MaterialBar source={slot.source} {...CHIP} />
                    {slot.source}
                  </span>
                </label>
              </li>
            ))}
            {slots.length === 0 && <li>no slot has drawn this part</li>}
          </ul>
          {turning && (
            <Suspense fallback={<p className="corpus-orbit-loading">loading the model…</p>}>
              <PartOrbit part={detail.part.id} />
            </Suspense>
          )}
          <div className="corpus-actions">
            <a className="corpus-action" href={`/index.html?part=${encodeURIComponent(partId)}`}
               target="_blank" rel="noopener noreferrer">Open in lab</a>
            <button type="button" className="corpus-action" aria-pressed={turning}
                    onClick={() => setTurning((was) => !was)}>
              {turning ? 'Hide 3D' : 'Turn it around'}
            </button>
            <button type="button" className="corpus-action" disabled={drawing}
                    onClick={() => void redrawShown()}>
              {drawing ? 'Drawing…' : `Redraw ${shown}`}
            </button>
            <label className="corpus-action-toggle">
              <input type="checkbox" checked={outlineTranslucent}
                     onChange={(e) => setOutlineTranslucent(e.target.checked)} />
              Outlines in translucent views
            </label>
            <button type="button"
                    className={flagging ? 'corpus-action' : 'corpus-action corpus-action-flag'}
                    onClick={() => setFlagging((was) => !was)}>
              {flagging ? 'Cancel' : 'Flag a problem'}
            </button>
            {/* Disarms on blur: an armed button left behind would fire on a
                click meant for something else the next time it had focus. */}
            <button type="button" className="corpus-action"
                    disabled={fixing === 'busy' || (unfixed === 0 && !flagged)}
                    onClick={() => void markFixed()}
                    onBlur={() => { if (fixing === 'armed') setFixing('idle'); }}>
              {fixLabel}
            </button>
          </div>
          {fixError && (
            <p className="corpus-flag-error" role="alert">Mark fixed failed: {fixError}</p>
          )}
          {queuedAt && (
            <p className="corpus-queued">
              Queued for the next {shown} round · asked {queuedAt.slice(0, 10)}
            </p>
          )}
          {redraw !== null && 'error' in redraw && (
            <p className="corpus-flag-error" role="alert">Redraw failed: {redraw.error}</p>
          )}
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
                  {catalog.key && catalog.key(detail.part.id) !== detail.part.id
                    && <> {catalog.key(detail.part.id)}</>}
                </a>
              </li>
            ))}
          </ul>
          <h3>Built from</h3>
          <Fingerprint features={detail.features} />
          <h3>Measurements</h3>
          <Measurements findings={detail.findings} />
          {detail.edges && detail.edges.length > 0 && (
            <>
              <h3>Declared edges</h3>
              <table>
                <thead>
                  <tr><th>slot</th><th>gaps</th><th>missing px</th>
                      <th>declared px</th></tr>
                </thead>
                <tbody>
                  {detail.edges.map((e) => (
                    <tr key={e.source}>
                      <td>{e.source}</td>
                      <td>{e.error ?? e.missing_comps ?? '—'}</td>
                      <td>{e.missing_len ?? '—'}</td>
                      <td>{e.declared_len ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
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
    {zoomedSlot && detail && (
      <ZoomView partId={detail.part.id} source={zoomedSlot.source}
                src={renderSrc(detail.part.id, zoomedSlot, outlineTranslucent)}
                onClose={() => setZoomedSlot(null)} />
    )}
    </>
  );

  return host ? createPortal(panel, host) : panel;
}
