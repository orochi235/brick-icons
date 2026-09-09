import type { Coverage } from '@lab/corpus/facts';
import type { CoverageRow, Phase, PhaseRow, SpeedRow } from '@lab/stats/types';

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

/** Every engine's render times in one plot, sharing bins and one count scale.
 *
 *  Overlaid rather than a small multiple per engine, because the question the
 *  section asks is which engine is faster and a reader cannot answer it across
 *  a gap. Scaling each panel to its own tallest bin actively lied: naive's
 *  10-30s bin and occt's drew the same height on different counts.
 *
 *  Identity is fill against hatch, not two hues. The status palette already
 *  spends gold, red and cyan and the phase palette blue, orange, green and
 *  purple; a spare hue on this page is one the reader has just been taught to
 *  read as something else. The hatch also survives being printed and being
 *  colorblind, which a hue pair does not. */
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

/** Every engine's slowest parts in one plot, sharing one seconds scale, on the
 *  reasoning `SecsOverlay` sets out: a panel per engine scaled to its own
 *  tallest part actively lied, drawing naive's 8-minute tail and occt's
 *  10-minute one at the same height. The x position is a RANK, not a part --
 *  each engine has its own 40 slowest, and what the section asks is whose tail
 *  is worse, which two rank profiles on one scale answer and two part lists
 *  side by side do not. Longest last, so the climb reads left to right.
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
