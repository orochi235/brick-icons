import { useCallback, useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { CostBars, CoverageBars, CoverageLegend, FailureLines, PhaseBars,
         PhaseColumns, PhaseLegend, SecsOverlay } from '@lab/stats/charts';
import { Footprint } from '@lab/stats/Footprint';
import { PhaseTree } from '@lab/stats/PhaseTree';
import type { Failures } from '@lab/stats/types';
import { useStats } from '@lab/stats/useStats';
import { DEFAULT_SET, fromQuery, toQuery, wallHref,
         type WorkingSet } from '@lab/stats/workingSet';
import '@lab/stats/stats.css';
import { LabSwitcher } from '@weasel-js/labkit';
import { PAGES } from '@lab/nav/pages';

const KINDS: { id: WorkingSet['kind']; label: string }[] = [
  { id: 'all', label: 'all parts' },
  { id: 'base', label: 'base parts' },
  { id: 'printed', label: 'printed' },
  { id: 'obsolete', label: 'obsolete' },
];

/** Categories big enough to be worth a checkbox of their own, and the badges
 *  worth narrowing by. Taken from the tallies themselves rather than a list
 *  here, so a category that appears in the library appears in the control. */
const CATEGORY_CUTOFF = 200;

function Controls({ set, onChange, categories }: {
  set: WorkingSet;
  onChange: (next: WorkingSet) => void;
  categories: [string, number][];
}) {
  const excluded = new Set(set.excluded);
  return (
    <div className="stats-controls">
      <label>
        Show
        <select value={set.kind}
                onChange={(e) => onChange({ ...set,
                                            kind: e.target.value as WorkingSet['kind'] })}>
          {KINDS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
        </select>
      </label>
      <label>
        <input type="checkbox" checked={set.outOfScope}
               onChange={(e) => onChange({ ...set, outOfScope: e.target.checked })} />
        out of scope
      </label>
      <label>
        <input type="checkbox" checked={set.moved}
               onChange={(e) => onChange({ ...set, moved: e.target.checked })} />
        moved
      </label>
      <fieldset className="stats-categories">
        <legend>Categories</legend>
        {categories.filter(([, n]) => n >= CATEGORY_CUTOFF).map(([name, n]) => (
          <label key={name}>
            <input type="checkbox" checked={!excluded.has(name)}
                   onChange={(e) => onChange({
                     ...set,
                     excluded: e.target.checked
                       ? set.excluded.filter((x) => x !== name)
                       : [...set.excluded, name],
                   })} />
            {name} <span className="stats-muted">{n.toLocaleString()}</span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}

/** Every tally the corpus database can answer for, over a working set you
 *  pick. The wall shows the same parts one cell at a time; this counts them. */
export function StatsPage({ client }: { client: LabClient }) {
  const [set, setSet] = useState<WorkingSet>(
    () => (typeof window === 'undefined'
      ? DEFAULT_SET : fromQuery(new URLSearchParams(window.location.search))));
  const { stats, error, busy, polling, reload } = useStats(client, set);

  // The address bar is the working set's only home: reload the page and you
  // get the same numbers, and the link you send names the same parts.
  useEffect(() => {
    const q = toQuery(set).toString();
    const next = q ? `?${q}` : window.location.pathname;
    window.history.replaceState(null, '', next);
  }, [set]);

  const change = useCallback((next: WorkingSet) => setSet(next), []);
  // A lab API older than this bundle sends no `failures`. Read through a
  // blank rather than off `stats.failures` directly: the page carries nine
  // other sections, and none of them should go dark over a stale server.
  // `unanswered` keeps that case apart from a real zero -- "nothing is
  // broken" and "this server cannot say" must not draw the same.
  const failures = stats?.failures ?? NO_FAILURES;
  const unanswered = stats !== null && stats.failures === undefined;
  const categories = stats?.shape.categories ?? [];
  const total = stats?.set.total ?? 0;

  return (
    <div className="lk-root stats-page">
      <header className="stats-head">
        <LabSwitcher title="corpus stats" pages={PAGES} />
        <p className="stats-asof">
          {stats
            ? <>{stats.set.size.toLocaleString()} of {total.toLocaleString()} parts
                {' · '}as of {stats.as_of.slice(11, 16)}
                {polling ? ' · a run is open, re-reading' : ''}
                {busy ? ' · reading…' : ''}</>
            : 'reading the corpus…'}
        </p>
        <button type="button" onClick={reload}>Reload</button>
      </header>

      <Controls set={set} onChange={change} categories={categories} />

      {error && <p className="stats-error" role="alert">{error}</p>}
      {!stats ? <p className="stats-empty">loading…</p> : (
        <>
          <section className="stats-tiles">
            <Tile n={unanswered ? null : failures.totals.occt.bad}
                  of={unanswered ? undefined : failures.totals.size} wide
                  label="parts occt cannot draw, corpus-wide" />
            <Tile n={unanswered ? null : failures.totals.decal.bad}
                  of={unanswered ? undefined : failures.totals.size} wide
                  label="parts decal cannot draw, corpus-wide" />
            <Tile n={stats.set.size} of={total} label="parts in the set" />
            <Tile n={stats.coverage.reduce((a, r) => a + r.counts.drawn, 0)}
                  label="renders across every slot" />
            <Tile n={stats.speed.reduce((a, r) => a + r.n, 0)}
                  label="timings, one per part per engine" />
            <Tile n={stats.shape.dated} of={stats.set.size}
                  label="carry set and year facts" />
          </section>

          <section>
            <h2>What will not draw</h2>
            <FailureLines rows={failures.series} unit="count"
                          caption={unanswered ? STALE_API
                            : 'no tally has been taken yet — one is written on '
                              + 'the next ingest'} />
            <p className="stats-note">
              Counted over every in-scope part, so the Controls above do not
              move these. A part failing in more than one occt facet is one
              line per facet here, and one part in the tile.
            </p>
          </section>

          <section>
            <h2>Failure rate by engine revision</h2>
            <FailureLines rows={failures.by_build} unit="rate"
                          caption={unanswered ? STALE_API
                            : 'no render in this corpus carries the build that '
                              + 'drew it'} />
            <p className="stats-note">
              A share, not a count, and on its own axis for that reason: each
              revision is measured over the parts it actually drew, which
              ranges from a handful to the whole library.
            </p>
          </section>

          <section>
            <h2>Coverage</h2>
            <CoverageLegend />
            <CoverageBars rows={stats.coverage}
                          onOpen={(row) => wallHref(set, row.source)} />
          </section>

          <section>
            <h2>What a pass costs</h2>
            {!stats.cost
              ? <p className="stats-empty">
                  no two slots have drawn the same parts at one recorded
                  engine revision yet
                </p>
              : (
                <>
                  <CostBars cost={stats.cost} />
                  <p className="stats-note">
                    One engine revision — <code>{stats.cost.build}</code> —
                    over the {stats.cost.n.toLocaleString()} parts it drew in
                    every slot above. Taken at one revision on purpose: a
                    slot's stored seconds span every engine that ever drew it,
                    and mixing them reverses which slot reads as the expensive
                    one. Running all {stats.cost.slots.length} costs{' '}
                    {(1 / (stats.cost.slots
                      .find((r) => r.source === stats.cost!.base)?.share ?? 1))
                      .toFixed(1)}× one {stats.cost.base} pass.
                  </p>
                </>
              )}
          </section>

          <section>
            <h2>Render seconds</h2>
            {stats.speed.length === 0
              ? <p className="stats-empty">nothing in this set has been timed</p>
              : (
                <SecsOverlay rows={stats.speed} />
              )}
          </section>

          <section>
            <h2>Where the time goes</h2>
            <PhaseLegend />
            <PhaseBars rows={stats.phases} />
            <PhaseColumns rows={stats.phases} />
          </section>

          <section>
            <h2>Inside a render</h2>
            {stats.phases.every((row) => row.split === null)
              ? <p className="stats-empty">
                  nothing in this set was measured with the render broken down
                </p>
              : stats.phases.map((row) => row.split && (
                <PhaseTree
                  key={row.engine}
                  nodes={row.split.nodes}
                  caption={`${row.engine} — over the `
                    + `${row.split.n.toLocaleString()} of `
                    + `${row.n.toLocaleString()} parts whose render named its `
                    + 'stages'} />
              ))}
          </section>

          <section>
            <h2>How far off</h2>
            <table>
              <thead>
                <tr><th>engine</th><th>parts</th><th>median d99</th><th>p95 d99</th>
                    <th>worst d99</th><th>median missing px</th></tr>
              </thead>
              <tbody>
                {stats.error.map((row) => (
                  <tr key={row.engine}>
                    <td>{row.engine}</td>
                    <td>{row.d99.n.toLocaleString()}</td>
                    <td>{fixed(row.d99.median)}</td>
                    <td>{fixed(row.d99.p95)}</td>
                    <td>{fixed(row.d99.max)}</td>
                    <td>{fixed(row.missing_px.median, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <Footprint client={client} />

          <section>
            <h2>What the set is made of</h2>
            <table>
              <thead><tr><th>category</th><th>parts</th></tr></thead>
              <tbody>
                {categories.slice(0, 20).map(([name, n]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{n.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}

const fixed = (v: number | null, places = 2) =>
  v === null ? '—' : v.toFixed(places);

const STALE_API = 'this lab API predates the failure tallies — restart it '
  + '(python -m brick_icons.lab) to see them';

const NO_FAILURES: Failures = {
  totals: { size: 0, occt: { bad: 0, failed: 0, timeout: 0, facets: [] },
            decal: { bad: 0, failed: 0, timeout: 0 } },
  series: [], by_build: [],
};

function Tile({ n, of, label, wide }: {
  n: number | null; of?: number; label: string; wide?: boolean;
}) {
  return (
    <div className={wide ? 'stats-tile stats-tile-wide' : 'stats-tile'}>
      <strong>{n === null ? '—' : n.toLocaleString()}</strong>
      {of !== undefined && <span className="stats-muted">of {of.toLocaleString()}</span>}
      <span className="stats-tile-label">{label}</span>
    </div>
  );
}
