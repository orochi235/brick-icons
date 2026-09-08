import { useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Footprint as FootprintData } from '@lab/stats/types';
import { humanBytes, share } from '@lab/stats/bytes';

/** The tiles, in the order they are drawn. `out` leads because it is the sum
 *  the other three sit inside. */
const TILES: { key: keyof FootprintData['tiles']; label: string }[] = [
  { key: 'out', label: 'out/' },
  { key: 'renders', label: 'renders' },
  { key: 'bakes', label: 'thumbnail bakes' },
  { key: 'lab_cache', label: 'lab cache' },
];

/** Counted, but not big enough or interesting enough to spend a tile on. */
const ASIDE: { key: keyof FootprintData['tiles']; label: string }[] = [
  { key: 'library', label: 'LDraw library' },
  { key: 'corpus_db', label: 'corpus.db' },
  { key: 'git', label: '.git' },
];

/** The corpus's footprint, read once rather than polled.
 *
 *  Its own hook and its own route: `useStats` re-reads every few seconds
 *  while a census runs, and walking `out/` is seconds over a few hundred
 *  thousand files. `refresh` forces the server past its own memo. */
export function useFootprint(client: LabClient) {
  const [data, setData] = useState<FootprintData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [nonce, setNonce] = useState(0);
  const live = useRef(true);
  const api = useRef(client);
  api.current = client;

  useEffect(() => {
    live.current = true;
    setBusy(true);
    void (async () => {
      try {
        const next = await api.current.corpusSizes(nonce > 0);
        if (!live.current) return;
        setData(next);
        setError(null);
      } catch (e) {
        if (!live.current) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (live.current) setBusy(false);
      }
    })();
    return () => { live.current = false; };
  }, [nonce]);

  return { data, error, busy, refresh: () => setNonce((n) => n + 1) };
}

export function Footprint({ client }: { client: LabClient }) {
  const { data, error, busy, refresh } = useFootprint(client);

  return (
    <section className="stats-footprint">
      <h2>
        Footprint
        <button type="button" onClick={refresh} disabled={busy}>
          {busy ? 'measuring…' : 'Re-measure'}
        </button>
      </h2>
      <p className="stats-muted">
        Size on disk, as <code>du</code> counts it — a 32px thumbnail is mostly
        block overhead, so its bytes and its blocks differ by half.
      </p>

      {error && <p className="stats-error" role="alert">{error}</p>}
      {!data ? <p className="stats-empty">measuring…</p> : (
        <>
          <div className="stats-tiles">
            {TILES.map(({ key, label }) => (
              <div className="stats-tile" key={key}>
                <strong>{humanBytes(data.tiles[key])}</strong>
                {key !== 'out' && (
                  <span className="stats-muted">
                    {pct(share(data.tiles[key], data.tiles.out))} of out/
                  </span>
                )}
                <span className="stats-tile-label">{label}</span>
              </div>
            ))}
          </div>

          <p className="stats-aside">
            {ASIDE.map(({ key, label }, i) => (
              <span key={key}>
                {i > 0 && ' · '}
                {label} <strong>{humanBytes(data.tiles[key])}</strong>
              </span>
            ))}
          </p>

          {data.slots.length > 0 && (
            <table className="stats-slot-sizes">
              <thead>
                <tr><th>slot</th><th>renders</th><th>bakes</th><th>total</th></tr>
              </thead>
              <tbody>
                {data.slots.map((slot) => (
                  <tr key={slot.source}>
                    <td>{slot.source}</td>
                    <td>{humanBytes(slot.renders)}</td>
                    <td>{humanBytes(slot.bakes)}</td>
                    <td>{humanBytes(slot.total)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>every slot</td>
                  <td>{humanBytes(sum(data.slots, 'renders'))}</td>
                  <td>{humanBytes(sum(data.slots, 'bakes'))}</td>
                  <td>{humanBytes(sum(data.slots, 'total'))}</td>
                </tr>
              </tfoot>
            </table>
          )}
        </>
      )}
    </section>
  );
}

const sum = (slots: FootprintData['slots'], key: 'renders' | 'bakes' | 'total') =>
  slots.reduce((a, s) => a + s[key], 0);

const pct = (v: number | null) => (v === null ? '—' : `${v.toFixed(0)}%`);
