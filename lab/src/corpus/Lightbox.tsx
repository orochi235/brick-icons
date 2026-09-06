import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { CATALOGS } from '@lab/corpus/catalogs';
import { Tags, yearRange } from '@lab/corpus/tags';
import { defectId, engineFor } from '@lab/corpus/flag';
import type { PartDetail } from '@lab/corpus/types';
import '@lab/corpus/Lightbox.css';

export function Lightbox({ partId, source, client, onClose }: {
  partId: string;
  source: string;
  client: LabClient;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PartDetail | null>(null);
  const [flagging, setFlagging] = useState(false);
  const [title, setTitle] = useState('');
  const [flagError, setFlagError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    void client.corpusPart(partId).then((d) => { if (live) setDetail(d); });
    return () => { live = false; };
  }, [partId, client]);

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
        engines: [engineFor(source)],
        status: 'open',
        title: title.trim(),
        filed: new Date().toISOString().slice(0, 10),
      });
      setTitle('');
      setFlagging(false);
      setDetail(await client.corpusPart(partId));
    } catch (e) {
      setFlagError(e instanceof Error ? e.message : String(e));
    }
  };
  const years = detail
    ? yearRange(detail.part.year_from, detail.part.year_to,
                (detail.part.tags ?? []).includes('retired'))
    : null;

  return (
    <div className="corpus-lightbox" role="dialog" aria-label={`Part ${partId}`}>
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
          <ul className="corpus-slots">
            {slots.map((slot) => (
              <li key={slot.source} className="corpus-slot"
                  data-current={slot.source === source}
                  data-retired={(detail.part.tags ?? []).includes('retired')}>
                <img className="corpus-big" alt={`${detail.part.id} drawn by ${slot.source}`}
                     src={`/api/corpus/render/${slot.source}/${detail.part.id}.svg`
                          + `?v=${slot.sha256.slice(0, 8)}`} />
                <span className="corpus-slot-name">{slot.source}</span>
              </li>
            ))}
            {slots.length === 0 && <li>no slot has drawn this part</li>}
          </ul>
          <div className="corpus-actions">
            <a className="corpus-action" href={`/index.html?part=${encodeURIComponent(partId)}`}
               target="_blank" rel="noopener noreferrer">Open in lab</a>
            <button type="button" className="corpus-action"
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
              <button type="submit" disabled={!title.trim()}>File against {source}</button>
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
              {detail.defects.map((d) => (
                <li key={d.id}>{d.title} <em>{d.status}</em></li>
              ))}
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
  );
}
