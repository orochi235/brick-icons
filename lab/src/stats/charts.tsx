import type { Coverage } from '@lab/corpus/facts';
import type { CoverageRow, Phase, PhaseRow, SpeedRow, SplitPhase } from '@lab/stats/types';

/** Stack order, worst news leftmost, so the eye lands on the problems before
 *  the bulk. Matches `COVERAGE_ORDER` in facts.ts and cells.py. */
export const STACK: Coverage[] = ['defect', 'failed', 'timeout', 'drawn', 'untried'];

export const COVERAGE_LABEL: Record<Coverage, string> = {
  defect: 'open defect',
  failed: 'render error',
  timeout: 'timed out',
  drawn: 'drawn',
  untried: 'never attempted',
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
export const SPLIT_STACK: SplitPhase[] = ['geometry', 'decoration', 'fill', 'rest'];

export const SPLIT_LABEL: Record<SplitPhase, string> = {
  geometry: 'geometry',
  decoration: 'decoration',
  fill: 'fill',
  rest: 'rest of the render',
};

const secs = (v: number) =>
  v >= 3600 ? `${(v / 3600).toFixed(1)}h` : v >= 60 ? `${(v / 60).toFixed(0)}m` : `${v.toFixed(1)}s`;

/** Where a working set's wall-clock went, one bar per engine.
 *
 *  The render band carries a second bar beneath it rather than sub-segments
 *  inside it: the split is tallied over its own much smaller n -- most of the
 *  census predates the instrumentation -- and nesting one denominator inside
 *  another reads as a single whole it is not. */
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
          {row.split && (
            <div className="stats-phase-split">
              <p className="stats-muted stats-phase-note">
                render splits, over the {row.split.n.toLocaleString()} of{' '}
                {row.n.toLocaleString()} parts measured since the split existed
              </p>
              <div className="stats-bar" role="img"
                   aria-label={`render splits into ${SPLIT_STACK
                     .map((k) => `${SPLIT_LABEL[k]} ${secs(row.split!.totals[k])}`)
                     .join(', ')}`}>
                {SPLIT_STACK.map((phase) => {
                  const v = row.split!.totals[phase];
                  if (v === 0) return null;
                  const share = pct(v, row.split!.total);
                  return (
                    <span key={phase} className="stats-seg" data-split={phase}
                          style={{ width: `${share}%` }}
                          title={`${SPLIT_LABEL[phase]} — ${secs(v)}, ${share.toFixed(1)}%`}>
                      {share >= 5 && (
                        <span className="stats-seg-label">
                          {SPLIT_LABEL[phase]}{share >= 12 && ` ${share.toFixed(0)}%`}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          )}
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

/** The slowest parts in the set, one stacked column each, longest last so the
 *  climb reads left to right the way the matplotlib probe drew it. */
export function PhaseColumns({ row }: { row: PhaseRow }) {
  const columns = [...row.slowest].reverse();
  const tallest = Math.max(1, ...columns.map((c) => c.total));
  return (
    <figure className="stats-columns">
      <figcaption className="stats-muted">
        the {columns.length} longest parts in this set — {row.engine},
        {' '}{secs(columns[columns.length - 1]?.total ?? 0)} at the tall end
      </figcaption>
      <div className="stats-column-plot">
        {columns.map((col) => {
          const label = `${col.part_id} — ${secs(col.total)}`;
          const body = PHASE_STACK.map((phase) => {
            const v = col.secs[phase];
            if (v === 0) return null;
            return <span key={phase} className="stats-col-seg stats-phase-mark" data-phase={phase}
                         style={{ height: `${pct(v, col.total)}%` }} />;
          });
          return (
            <div key={col.part_id} className="stats-column"
                 style={{ height: `${pct(col.total, tallest)}%` }} title={label}>
              <span className="stats-column-stack" aria-label={label}>{body}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
