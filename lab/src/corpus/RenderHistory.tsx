import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PartHistory } from '@lab/corpus/types';
import { familyInk, materialOf } from '@lab/shared/materials';
import { ticksFor } from '@lab/stats/charts';
import '@lab/corpus/RenderHistory.css';

type Point = PartHistory['series'][number]['points'][number];

const METRICS: { key: 'secs' | 'bytes' | 'objects'; label: string;
                 scale: number; format: (v: number) => string }[] = [
  { key: 'secs', label: 'render time (s)', scale: 1, format: (v) => v.toFixed(1) },
  { key: 'bytes', label: 'file size (KB)', scale: 1 / 1024, format: (v) => v.toFixed(1) },
  { key: 'objects', label: 'visible objects', scale: 1, format: (v) => v.toFixed(0) },
];

const W = 360, H = 130, PAD_L = 44, PAD_R = 10, PAD_T = 8, PAD_B = 22;

function Panel({ points, metric, t0, t1, ink }: {
  points: Point[]; metric: typeof METRICS[number]; t0: number; t1: number; ink: string;
}) {
  const known = points.filter((p) => p[metric.key] != null);
  const value = (p: Point) => (p[metric.key] as number) * metric.scale;
  const ticks = ticksFor(Math.max(0, ...known.map(value)));
  const top = ticks[ticks.length - 1] || 1;
  const x = (p: Point) => PAD_L + (t1 === t0 ? (W - PAD_L - PAD_R) / 2
    : ((Date.parse(p.at) - t0) / (t1 - t0)) * (W - PAD_L - PAD_R));
  const y = (v: number) => H - PAD_B - (v / top) * (H - PAD_T - PAD_B);
  const d = known.map((p, i) => `${i ? 'L' : 'M'}${x(p).toFixed(1)},${y(value(p)).toFixed(1)}`)
    .join(' ');
  return (
    <figure className="corpus-history-panel">
      <figcaption>{metric.label}</figcaption>
      {known.length === 0 ? (
        <p className="corpus-history-empty">nothing recorded</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={metric.label}>
          {ticks.map((t) => (
            <g key={t}>
              <line className="corpus-history-grid" x1={PAD_L} x2={W - PAD_R} y1={y(t)} y2={y(t)} />
              <text className="corpus-history-axis" x={PAD_L - 6} y={y(t) + 4} textAnchor="end">
                {metric.format(t)}
              </text>
            </g>
          ))}
          <text className="corpus-history-axis" x={PAD_L} y={H - 6}>
            {new Date(t0).toISOString().slice(5, 10)}
          </text>
          {t1 !== t0 && (
            <text className="corpus-history-axis" x={W - PAD_R} y={H - 6} textAnchor="end">
              {new Date(t1).toISOString().slice(5, 10)}
            </text>
          )}
          <path className="corpus-history-line" d={d} stroke={ink} />
          {known.map((p) => (
            <g key={`${p.run_id}:${p.at}`} className="corpus-history-point">
              <circle className="corpus-history-hit" cx={x(p)} cy={y(value(p))} r={8} />
              <circle className="corpus-history-dot" cx={x(p)} cy={y(value(p))} r={4}
                      stroke={ink} fill={p.dated_by === 'drawn' ? ink : 'none'} />
              <title>
                {`${p.at.slice(0, 16).replace('T', ' ')} — ${metric.format(value(p))}`}
                {p.build ? ` — build ${p.build}` : ''}
                {p.dated_by === 'build' ? ' — dated by its engine commit' : ''}
              </title>
            </g>
          ))}
        </svg>
      )}
    </figure>
  );
}

/** One slot's measurements of this part over calendar time: time, size and
 *  painted objects, one small chart each since they share no scale. */
export function RenderHistory({ partId, source, client }: {
  partId: string; source: string; client: LabClient;
}) {
  const [history, setHistory] = useState<PartHistory | null>(null);
  useEffect(() => {
    let live = true;
    void client.corpusPartHistory?.(partId).then((h) => { if (live) setHistory(h); });
    return () => { live = false; };
  }, [partId, client]);

  if (!history) return null;
  const points = (history.series.find((s) => s.source === source)?.points ?? [])
    .filter((p) => !p.error);
  if (points.length === 0) {
    return <p className="corpus-history-empty">no measurements of {source} for this part</p>;
  }
  const times = points.map((p) => Date.parse(p.at));
  const ink = familyInk(materialOf(source));
  return (
    <div className="corpus-history">
      <div className="corpus-history-panels">
        {METRICS.map((m) => (
          <Panel key={m.key} points={points} metric={m} ink={ink}
                 t0={Math.min(...times)} t1={Math.max(...times)} />
        ))}
      </div>
      <p className="corpus-history-note">
        {source}, {points.length} measurements. A filled dot is dated by when its
        drawing was written; a hollow one, whose drawing was gone, by its engine commit.
      </p>
    </div>
  );
}
