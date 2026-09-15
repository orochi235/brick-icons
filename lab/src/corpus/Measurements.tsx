import type { PartDetail } from '@lab/corpus/types';
import { MaterialBar } from '@lab/shared/MaterialBar';
import { chartRank } from '@lab/shared/materials';
import '@lab/corpus/Measurements.css';

type Finding = PartDetail['findings'][number];
type Measure = 'extra_d99' | 'missing_px' | 'missing_comps';

// Latest measurement per part and slot in corpus.db, 2026-09-15.
export const CUTOFFS: Record<Measure, readonly [p90: number, p99: number]> = {
  extra_d99: [1.41, 7.44],
  missing_px: [724, 61026],
  missing_comps: [1, 6],
};

export function tier(measure: Measure, value: number | null | undefined):
    'warm' | 'hot' | undefined {
  if (value == null) return undefined;
  const [p90, p99] = CUTOFFS[measure];
  return value >= p99 ? 'hot' : value >= p90 ? 'warm' : undefined;
}

const COLUMNS: { key: Measure; label: string; format: (v: number) => string }[] = [
  { key: 'extra_d99', label: 'extra d99', format: (v) => v.toFixed(2) },
  { key: 'missing_px', label: 'missing px', format: (v) => v.toLocaleString() },
  { key: 'missing_comps', label: 'missing comps', format: (v) => String(v) },
];

const TRACK = 300;
const CHIP = { width: 34, height: 14 };

const slotOf = (f: Finding) => f.source ?? f.engine;

export function Measurements({ findings }: { findings: Finding[] }) {
  const rows = [...findings].sort((a, b) => chartRank(slotOf(a)) - chartRank(slotOf(b)));
  const slowest = Math.max(0, ...rows.map((f) => f.secs ?? 0)) || 1;
  return (
    <table className="corpus-measures">
      <thead>
        <tr>
          <th />
          {COLUMNS.map((c) => <th key={c.key} className="corpus-measure-num">{c.label}</th>)}
          <th>secs</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((f) => {
          const slot = slotOf(f);
          const timedOut = /timeout/i.test(f.error ?? '');
          // `source` is nullable in the DB, so two findings can share a display
          // slot; key by the row's own identity, not the name it renders.
          const key = `${f.part_id}:${f.engine}:${f.source ?? ''}`;
          return (
            <tr key={key} data-slot={slot}>
              <th scope="row" className="corpus-measure-slot">
                <span className="corpus-chip-label">
                  <MaterialBar source={slot} {...CHIP} />{slot}
                </span>
              </th>
              {f.error ? (
                <td colSpan={COLUMNS.length} className="corpus-measure-error">{f.error}</td>
              ) : COLUMNS.map((c) => {
                const value = f[c.key];
                return (
                  <td key={c.key} className="corpus-measure-num" data-tier={tier(c.key, value)}>
                    {value == null ? '—' : c.format(value)}
                  </td>
                );
              })}
              <td>
                <span className="corpus-measure-bar">
                  {f.secs != null && (
                    <MaterialBar source={slot} width={Math.max(3, (f.secs / slowest) * TRACK)}
                                 height={18} timedOut={timedOut} />
                  )}
                  <span className="corpus-measure-value" data-timed-out={timedOut || undefined}>
                    {f.secs == null ? '—' : `${f.secs.toFixed(1)}s`}
                  </span>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
