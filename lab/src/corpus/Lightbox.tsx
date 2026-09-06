import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PartDetail } from '@lab/corpus/types';
import '@lab/corpus/Lightbox.css';

export function Lightbox({ partId, source, client, onClose }: {
  partId: string;
  source: string;
  client: LabClient;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<PartDetail | null>(null);
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
          </p>
          <img className="corpus-big" alt={`${detail.part.id} render`}
               src={`/api/thumbs/${source}/128/${detail.part.id}.png`} />
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
