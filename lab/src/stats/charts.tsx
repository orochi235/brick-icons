import type { Coverage } from '@lab/corpus/facts';
import type { Cost, CoverageRow, Phase, PhaseRow, SpeedRow } from '@lab/stats/types';

/** Stack order: `drawn` leads, so a row reads from the left as how much of
 *  the slot is done, the way any progress bar does, and the rows can be
 *  compared to each other by one edge. The problem states keep the middle,
 *  between two neutrals, which is where their saturation finds the eye; the
 *  bulk of untried sits last. Deliberately NOT `COVERAGE_ORDER` (facts.ts,
 *  cells.py) -- that one ranks a cell's states worst-first for the wall's
 *  grouping, and nothing here depends on the two agreeing. */
export const STACK: Coverage[] =
  ['drawn', 'defect', 'failed', 'timeout', 'untried', 'notApplicable'];

export const COVERAGE_LABEL: Record<Coverage, string> = {
  defect: 'open defect',
  failed: 'render error',
  timeout: 'timed out',
  drawn: 'drawn',
  untried: 'never attempted',
  // The wall's own words for this state (`states.ts`), so the chart and the
  // wall are one vocabulary rather than two names for one thing.
  notApplicable: 'nothing for this slot to draw',
};

/** A status palette, not a categorical one. The values live in `stats.css`
 *  as `--stats-<label>`; this record is the same list for anything that has
 *  to reason about it rather than paint with it. The three problem states keep the
 *  saturated border colors the wall marks them with, so a wall reader knows
 *  them on sight; `drawn` and `untried` are deliberately neutral, because the
 *  chart's job is to make the problems findable in a bar the other two own.
 *
 *  Validated with the dataviz validator against the dark surface: CVD
 *  separation, normal-vision separation and contrast all pass. Its lightness
 *  band and chroma floor fail by construction -- both demand every hue be
 *  equally loud, which is the opposite of what a status ramp is for. */
export const COVERAGE_COLOR: Record<Coverage, string> = {
  defect: '#daa520',
  failed: '#e03030',
  timeout: '#30b0d0',
  drawn: '#d8d8dc',
  untried: '#6a6a72',
  // Darker than `untried` and unsaturated: a part this slot was never going to
  // draw is not work outstanding, and must not read as any of the states that
  // are. Matches the wall's `notApplicableBorder`.
  notApplicable: '#3f3f46',
};

const pct = (n: number, whole: number) => (whole > 0 ? (n / whole) * 100 : 0);

/** One row per slot, each a full-width stack of the five coverage labels.
 *
 *  Segments are separated by a 2px surface gap rather than a stroke, so a
 *  one-part segment is still visible as a sliver instead of being swallowed
 *  by its neighbor's border. */
export function CoverageBars({ rows, onOpen }: {
  rows: CoverageRow[];
  onOpen?: (row: CoverageRow, label: Coverage) => string;
}) {
  if (rows.length === 0) return <p className="stats-empty">no slot has drawn anything yet</p>;
  return (
    <div className="stats-bars">
      {rows.map((row) => (
        <div key={row.source} className="stats-bar-row">
          <span className="stats-bar-name">{row.source}</span>
          <div className="stats-bar" role="img"
               aria-label={`${row.source}: ${STACK
                 .map((k) => `${row.counts[k].toLocaleString()} ${COVERAGE_LABEL[k]}`)
                 .join(', ')}`}>
            {STACK.map((label) => {
              const n = row.counts[label];
              if (n === 0) return null;
              const width = `${pct(n, row.size)}%`;
              const href = onOpen?.(row, label);
              const title = `${n.toLocaleString()} ${COVERAGE_LABEL[label]}`;
              // Only the width is inline: it is computed per datum and has
              // no class to live in. The fill is a data attribute the
              // stylesheet colors, so the palette stays in one file.
              return href ? (
                <a key={label} className="stats-seg" data-label={label}
                   style={{ width }} href={href} title={title} aria-label={title} />
              ) : (
                <span key={label} className="stats-seg" data-label={label}
                      style={{ width }} title={title} />
              );
            })}
          </div>
          <span className="stats-bar-value">
            {row.counts.drawn.toLocaleString()}
            <span className="stats-muted"> / {row.size.toLocaleString()}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** What one pass costs, slot by slot, as a share of running them all.
 *
 *  One bar each rather than a single stack: the question is how the slots
 *  compare to each other, and a stack answers that only for the segment
 *  touching an edge. The bars share a scale, so the widths are comparable
 *  across rows. */
export function CostBars({ cost }: { cost: Cost }) {
  const widest = Math.max(...cost.slots.map((r) => r.share));
  return (
    <div className="stats-bars stats-cost">
      <div className="stats-bar-row stats-cost-row stats-cost-head">
        <span />
        <span />
        <span className="stats-bar-value">share</span>
        <span className="stats-bar-value">&times; {cost.base}</span>
        <span className="stats-bar-value">median</span>
      </div>
      {cost.slots.map((row) => (
        <div key={row.source} className="stats-bar-row stats-cost-row">
          <span className="stats-bar-name">{row.source}</span>
          <div className="stats-bar" role="img"
               aria-label={`${row.source}: ${(row.share * 100).toFixed(1)}% of `
                 + `the seconds, ${row.ratio?.toFixed(2) ?? '?'} times `
                 + `${cost.base}`}>
            <span className="stats-seg" data-label="cost"
                  style={{ width: `${pct(row.share, widest)}%` }} />
          </div>
          <span className="stats-bar-value">{(row.share * 100).toFixed(1)}%</span>
          <span className="stats-bar-value">
            &times;{row.ratio === null ? '—' : row.ratio.toFixed(2)}
          </span>
          <span className="stats-bar-value">
            {row.median === null ? '—' : row.median.toFixed(1)}
            <span className="stats-muted">s</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export function CoverageLegend() {
  return (
    <ul className="stats-legend">
      {STACK.map((label) => (
        <li key={label}>
          <span className="stats-swatch" data-label={label} aria-hidden="true" />
          {COVERAGE_LABEL[label]}
        </li>
      ))}
    </ul>
  );
}

const binLabel = (from: number, to: number | null) =>
  to === null ? `${from}s+` : `${from}–${to}s`;

/** Render times, sharing bins and one count scale across whatever engines are
 *  on screen -- occt alone today. The shared scale is the load-bearing part:
 *  a panel scaled to its own tallest bin draws two different counts at the
 *  same height, so a second engine must not bring per-panel scaling with it.
 *
 *  Identity is fill against hatch, not two hues. The status palette already
 *  spends gold, red and cyan and the phase palette blue, orange, green and
 *  purple; a spare hue on this page is one the reader has just been taught to
 *  read as something else. */
const SERIES_FILL = ['solid', 'hatch'] as const;

export function SecsOverlay({ rows }: { rows: SpeedRow[] }) {
  const bins = rows[0]?.bins ?? [];
  const tallest = Math.max(1, ...rows.flatMap((r) => r.bins.map((b) => b.n)));
  return (
    <figure className="stats-histogram stats-overlay">
      <figcaption className="stats-overlay-keys">
        {rows.map((row, i) => (
          <span key={row.engine} className="stats-overlay-key">
            <span className="stats-swatch stats-bin-mark" aria-hidden="true"
                  data-fill={SERIES_FILL[i] ?? 'solid'} />
            <strong>{row.engine}</strong>
            <span className="stats-muted">
              {' '}median {row.median?.toFixed(1)}s · p95 {row.p95?.toFixed(0)}s ·
              {' '}max {row.max?.toFixed(0)}s · {row.n.toLocaleString()} parts
            </span>
          </span>
        ))}
      </figcaption>
      <div className="stats-bins">
        {bins.map((bin, b) => {
          const counts = rows.map((row) => row.bins[b]?.n ?? 0);
          // Both bars stand on the baseline, so the taller one hides the
          // shorter completely unless the shorter is the one in front. Which
          // engine that is changes bin by bin -- that is the whole point of
          // the chart -- so it cannot be a fixed order.
          const shortest = Math.min(...counts);
          return (
            <div key={bin.from} className="stats-bin">
              <span className="stats-bin-stack">
                {rows.map((row, i) => {
                  const n = counts[i] ?? 0;
                  return (
                    <span key={row.engine} className="stats-bin-fill stats-bin-mark"
                          data-engine={row.engine} data-fill={SERIES_FILL[i] ?? 'solid'}
                          data-front={n === shortest || undefined}
                          style={{ height: `${pct(n, tallest)}%`,
                                   zIndex: n === shortest ? 2 : 1 }}
                          title={`${row.engine}: ${n.toLocaleString()} parts took `
                                 + binLabel(bin.from, bin.to)} />
                  );
                })}
              </span>
              <span className="stats-bin-label">{binLabel(bin.from, bin.to)}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

/** The four exclusive phases, in the order a census row runs them. */
export const PHASE_STACK: Phase[] = ['render', 'rasterize', 'truth_mask', 'compare'];

export const PHASE_LABEL: Record<Phase, string> = {
  render: 'render',
  rasterize: 'rasterize',
  truth_mask: 'truth mask',
  compare: 'compare',
};

/** How `render` divides, in pipeline order. */
const secs = (v: number) =>
  v >= 3600 ? `${(v / 3600).toFixed(1)}h` : v >= 60 ? `${(v / 60).toFixed(0)}m` : `${v.toFixed(1)}s`;

/** Where a working set's wall-clock went, one bar per engine.
 *
 *  The four bands only. How `render` divides is `PhaseTree`'s: it is tallied
 *  over its own much smaller n -- most of the census predates the
 *  instrumentation -- and nesting one denominator inside another reads as a
 *  single whole it is not. */
export function PhaseBars({ rows }: { rows: PhaseRow[] }) {
  if (rows.length === 0) {
    return <p className="stats-empty">nothing in this set carries phase timings</p>;
  }
  return (
    <div className="stats-phases">
      {rows.map((row) => (
        <figure key={row.engine} className="stats-phase-engine">
          <figcaption>
            <strong>{row.engine}</strong>
            <span className="stats-muted">
              {' '}{secs(row.total)} over {row.n.toLocaleString()} parts
            </span>
          </figcaption>
          <div className="stats-bar" role="img"
               aria-label={`${row.engine}: ${PHASE_STACK
                 .map((k) => `${PHASE_LABEL[k]} ${secs(row.totals[k])}`).join(', ')}`}>
            {PHASE_STACK.map((phase) => {
              const v = row.totals[phase];
              if (v === 0) return null;
              return (
                <span key={phase} className="stats-seg stats-phase-mark" data-phase={phase}
                      style={{ width: `${pct(v, row.total)}%` }}
                      title={`${PHASE_LABEL[phase]} — ${secs(v)}, `
                             + `${pct(v, row.total).toFixed(1)}%`} />
              );
            })}
          </div>
        </figure>
      ))}
    </div>
  );
}

export function PhaseLegend() {
  return (
    <ul className="stats-legend">
      {PHASE_STACK.map((phase) => (
        <li key={phase}>
          <span className="stats-swatch stats-phase-mark" data-phase={phase} aria-hidden="true" />
          {PHASE_LABEL[phase]}
        </li>
      ))}
    </ul>
  );
}

/** The slowest parts, sharing one seconds scale, on the reasoning
 *  `SecsOverlay` sets out. The x position is a RANK, not a part -- each engine
 *  has its own 40 slowest, and what the section asks is how bad the tail is,
 *  which a rank profile answers and a part list does not. Longest last, so the
 *  climb reads left to right.
 *
 *  Identity is the same fill-against-hatch the histogram uses, and for the
 *  same reason: the columns are already spending four hues on the phases, so
 *  a fifth for the engine is one the reader has just been taught to read as
 *  something else. Here the hatch lies OVER whatever the phase painted. */
export function PhaseColumns({ rows }: { rows: PhaseRow[] }) {
  const series = rows.map((row) => ({ row, cols: [...row.slowest].reverse() }));
  const ranks = Math.max(0, ...series.map((s) => s.cols.length));
  const tallest = Math.max(1, ...series.flatMap((s) => s.cols.map((c) => c.total)));
  if (ranks === 0) return null;
  return (
    <figure className="stats-columns stats-overlay">
      <figcaption className="stats-overlay-keys">
        {series.map(({ row, cols }, i) => (
          <span key={row.engine} className="stats-overlay-key">
            <span className="stats-swatch stats-phase-mark" aria-hidden="true"
                  data-phase="render" data-fill={SERIES_FILL[i] ?? 'solid'} />
            <strong>{row.engine}</strong>
            <span className="stats-muted">
              {' '}the {cols.length} longest ·
              {' '}{secs(cols[cols.length - 1]?.total ?? 0)} at the tall end
            </span>
          </span>
        ))}
      </figcaption>
      <div className="stats-column-plot">
        {Array.from({ length: ranks }, (_, r) => {
          const at = series.map((s) => s.cols[r]);
          // Both series stand on the baseline, so the taller hides the shorter
          // unless the shorter is in front — and which engine that is changes
          // rank by rank, which is the whole point of the chart.
          const shortest = Math.min(...at.map((c) => c?.total ?? Infinity));
          return (
            <div key={r} className="stats-column">
              {at.map((col, i) => {
                if (!col) return null;
                const label = `${series[i]!.row.engine} #${r + 1}: `
                  + `${col.part_id} — ${secs(col.total)}`;
                const front = col.total === shortest;
                return (
                  <span key={series[i]!.row.engine} className="stats-col-series"
                        data-front={front || undefined}
                        style={{ height: `${pct(col.total, tallest)}%`,
                                 zIndex: front ? 2 : 1 }}
                        title={label}>
                    <span className="stats-column-stack" aria-label={label}>
                      {PHASE_STACK.map((phase) => {
                        const v = col.secs[phase];
                        if (v === 0) return null;
                        return <span key={phase}
                                     className="stats-col-seg stats-phase-mark"
                                     data-phase={phase}
                                     data-fill={SERIES_FILL[i] ?? 'solid'}
                                     style={{ height: `${pct(v, col.total)}%` }} />;
                      })}
                    </span>
                  </span>
                );
              })}
            </div>
          );
        })}
      </div>
    </figure>
  );
}

/** The slots the failure chart follows, in a fixed order, each keeping its hue
 *  however many are on screen. Color follows the SLOT, never its rank: a
 *  filter that drops one must not repaint the others.
 *
 *  Categorical, not the status palette above -- these say which slot, not how
 *  bad, and `--stats-failed` red is reserved for the state. Dark steps of the
 *  default eight-hue theme; validated against this page's sunken surface, all
 *  six checks pass (worst adjacent CVD dE 8.4, normal-vision 19.3). */
export const SLOT_ORDER = ['occt', 'white-occt', 'silhouette-occt',
                           'translucent-occt', 'decal'] as const;

export const SLOT_COLOR: Record<string, string> = {
  'occt': '#3987e5',
  'white-occt': '#d95926',
  'silhouette-occt': '#199e70',
  'translucent-occt': '#c98500',
  'decal': '#d55181',
};

const slotRank = (source: string) => {
  const i = (SLOT_ORDER as readonly string[]).indexOf(source);
  return i === -1 ? SLOT_ORDER.length : i;
};

interface FailurePoint { at: string; source: string; bad: number; size: number;
                         build: string | null }

/** Ticks that land on round numbers, so the axis reads without arithmetic.
 *
 *  The step list is finer than 1/2/5 on purpose: with three choices a max of
 *  2,532 rounds up to 5,000 and the data uses half the panel. */
const NICE = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

function ticksFor(max: number): number[] {
  if (max <= 0) return [0];
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  const scaled = max / step;
  const top = (NICE.find((n) => scaled <= n) ?? 10) * step;
  return [0, top / 4, top / 2, (top * 3) / 4, top];
}

/** Failures over time, one line per slot.
 *
 *  `unit` is `count` for the tallies and `rate` for the build prefix, and the
 *  two are never drawn on one pair of axes: a build that drew 11 parts and a
 *  corpus of 23,339 share no y-scale, and putting them together would read a
 *  tiny sample as a collapse in failures. */
export function FailureLines({ rows, unit, caption }: {
  rows: FailurePoint[];
  unit: 'count' | 'rate';
  caption: string;
}) {
  const value = (r: FailurePoint) =>
    unit === 'rate' ? (r.size > 0 ? (r.bad / r.size) * 100 : 0) : r.bad;

  const bySlot = new Map<string, FailurePoint[]>();
  for (const r of rows) {
    if (!bySlot.has(r.source)) bySlot.set(r.source, []);
    bySlot.get(r.source)!.push(r);
  }
  const slots = [...bySlot.keys()].sort((a, b) => slotRank(a) - slotRank(b));
  if (slots.length === 0) {
    return <p className="stats-empty">{caption}</p>;
  }

  const times = rows.map((r) => Date.parse(r.at));
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const top = Math.max(...ticksFor(Math.max(...rows.map(value))));

  const W = 720, H = 260, padL = 52, padR = 16, padT = 12, padB = 30;
  const x = (at: string) => padL + (t1 === t0 ? (W - padL - padR) / 2
    : ((Date.parse(at) - t0) / (t1 - t0)) * (W - padL - padR));
  const y = (v: number) => H - padB - (top === 0 ? 0 : (v / top) * (H - padT - padB));
  const ticks = ticksFor(Math.max(...rows.map(value)));
  const day = (at: string) => at.slice(5, 10);

  return (
    <figure className="stats-failures">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={caption}
           preserveAspectRatio="xMidYMid meet">
        {ticks.map((t) => (
          <g key={t}>
            <line className="stats-gridline" x1={padL} x2={W - padR}
                  y1={y(t)} y2={y(t)} />
            <text className="stats-axis" x={padL - 8} y={y(t) + 4}
                  textAnchor="end">
              {unit === 'rate' ? `${t.toFixed(0)}%` : t.toLocaleString()}
            </text>
          </g>
        ))}
        <text className="stats-axis" x={padL} y={H - 8}>{day(rows[0]!.at)}</text>
        {t1 !== t0 && (
          <text className="stats-axis" x={W - padR} y={H - 8} textAnchor="end">
            {day(rows[rows.length - 1]!.at)}
          </text>
        )}

        {slots.map((slot) => {
          const points = [...bySlot.get(slot)!].sort(
            (a, b) => Date.parse(a.at) - Date.parse(b.at));
          const d = points.map((p, i) =>
            `${i === 0 ? 'M' : 'L'}${x(p.at).toFixed(1)},${y(value(p)).toFixed(1)}`
          ).join(' ');
          return (
            <g key={slot}>
              <path className="stats-failure-line" data-slot={slot} d={d} />
              {points.map((p) => (
                <circle key={p.at} className="stats-failure-dot"
                        data-slot={slot} cx={x(p.at)} cy={y(value(p))} r={4}>
                  <title>
                    {`${slot} — ${p.at.slice(0, 16).replace('T', ' ')}`}
                    {unit === 'rate'
                      ? ` — ${value(p).toFixed(1)}% of ${p.size.toLocaleString()} drawn`
                      : ` — ${p.bad.toLocaleString()} of ${p.size.toLocaleString()}`}
                    {p.build ? ` — ${p.build}` : ''}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
      {t1 === t0 && (
        <p className="stats-note">
          One tally so far, so this is where the corpus stands rather than
          where it is going. A step appears each time an ingest moves a slot.
        </p>
      )}
      <figcaption className="stats-legend">
        {slots.map((slot) => (
          <span key={slot} className="stats-legend-item">
            <span className="stats-swatch" data-slot={slot} />
            {slot}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
