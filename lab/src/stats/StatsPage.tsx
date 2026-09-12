import { useCallback, useEffect, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { CostBars, CoverageBars, CoverageLegend, ELSEWHERE, isThin, SlotLines,
         PhaseBars, PhaseLegend, SecsOverlay, THIN } from '@lab/stats/charts';
import { Footprint } from '@lab/stats/Footprint';
import type { Cost, Failures } from '@lab/stats/types';
import { useStats } from '@lab/stats/useStats';
import { DEFAULT_VIEWPORT, fromHash, toHash } from '@lab/stats/viewport';
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
      <label>
        <input type="checkbox" checked={set.obsolete}
               onChange={(e) => onChange({ ...set, obsolete: e.target.checked })} />
        obsolete
      </label>
      <label>
        <input type="checkbox" checked={set.posed}
               onChange={(e) => onChange({ ...set, posed: e.target.checked })} />
        posed
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
/** The slots whose seconds do not all come from the panel's revision. */
const elsewhere = (cost: Cost) =>
  cost.slots.filter((row) => row.build !== cost.build || row.revisions > 1);

/** The slots whose ratio rests on a slice of the base's parts. */
const thin = (cost: Cost) =>
  cost.slots.filter((row) => isThin(row, cost));

/** "a, b and c" -- the footnote names every thin slot and there are usually
 *  two or three. */
function sentence(parts: string[]): string {
  if (parts.length < 2) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

/** The same set with one member turned on or off. */
const drop = (was: ReadonlySet<string>, key: string): ReadonlySet<string> => {
  const next = new Set(was);
  if (!next.delete(key)) next.add(key);
  return next;
};

export function StatsPage({ client }: { client: LabClient }) {
  const [set, setSet] = useState<WorkingSet>(
    () => (typeof window === 'undefined'
      ? DEFAULT_SET : fromQuery(new URLSearchParams(window.location.search))));
  const { stats, error, busy, polling, reload } = useStats(client, set);
  // Where the page was left: scroll and the bands clicked off, out of the
  // hash. In the hash rather than the query because none of it changes which
  // parts are counted -- see `viewport.ts`.
  const opened = useRef(typeof window === 'undefined'
    ? DEFAULT_VIEWPORT : fromHash(window.location.hash));
  const [hiddenCoverage, setHiddenCoverage] =
    useState<ReadonlySet<string>>(() => new Set(opened.current.hide));
  const [hiddenPhases, setHiddenPhases] =
    useState<ReadonlySet<string>>(() => new Set(opened.current.hidePhase));

  // The address bar is the working set's only home: reload the page and you
  // get the same numbers, and the link you send names the same parts. The
  // hash rides along untouched -- writing the query alone drops it, and the
  // place you were reading with it.
  useEffect(() => {
    const q = toQuery(set).toString();
    window.history.replaceState(
      null, '', `${window.location.pathname}${q ? `?${q}` : ''}`
               + `${window.location.hash}`);
  }, [set]);

  // Scroll is written straight to the address rather than held in state: it
  // changes on every wheel notch, and a page this size must not repaint for
  // it. Coalesced to one write a frame.
  useEffect(() => {
    let queued = 0;
    const write = () => {
      queued = 0;
      const hash = toHash({
        y: window.scrollY,
        hide: [...hiddenCoverage],
        hidePhase: [...hiddenPhases],
      });
      window.history.replaceState(
        null, '', `${window.location.pathname}${window.location.search}`
                 + `${hash ? `#${hash}` : ''}`);
    };
    const onScroll = () => {
      if (!queued) queued = window.requestAnimationFrame(write);
    };
    write();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (queued) window.cancelAnimationFrame(queued);
    };
  }, [hiddenCoverage, hiddenPhases]);

  // Put the reader back, once, after the tallies arrive: the page is a
  // spinner until then and has nothing to scroll through.
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !stats) return;
    restored.current = true;
    if (opened.current.y > 0) window.scrollTo(0, opened.current.y);
  }, [stats]);

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

          {/* Side by side, each description under its own chart: they share
              an x-axis and are read against each other, and stacked
              full-width the second was a scroll away from the first. One
              absolute and one share -- a third chart plotting the counts as a
              share of each slot's set moved with the coverage beside it and
              said nothing the pair does not. */}
          <div className="stats-pair">
            <section>
              <h2>What will not draw</h2>
              <SlotLines rows={failures.series} unit="count" compact
                            caption={unanswered ? STALE_API
                              : 'no tally has been taken yet — one is written on '
                                + 'the next ingest'} />
              <p className="stats-note">
                Counted over every in-scope part, so the Controls above do not
                move these. A part failing in more than one occt facet is one
                line per facet here, and one part in the tile. Counts, so the
                slots do not compare directly: decal&rsquo;s 2,532 are a fifth
                of what it draws where occt&rsquo;s 655 are a thirtieth.
              </p>
            </section>

            <section>
              <h2>Coverage over time</h2>
              <SlotLines rows={failures.series} unit="coverage" compact
                         caption={unanswered ? STALE_API
                           : 'no tally has been taken yet'} />
              <p className="stats-note">
                How much of what each slot was ever going to draw it has
                drawn. A share of its own slot&rsquo;s set, not of the library
                — decal draws printed parts and nothing else, and obsolete
                moulds are outside every slot, so against the whole corpus
                decal read as short of a library nothing asked it about.
              </p>
            </section>

          </div>

          <p className="stats-note">
            One axis across both: every tally, dated by when it was
            taken. They start where the tallies do, because nothing before
            that has a date — a rebuild restamped all 45 earlier ingests, 33
            of them inside one four-minute window. Dating a revision by its
            commit instead put six days on the axis for work that all ingested
            over two, which is why these no longer read builds. The run-axis
            history and the by-revision rates are still in the API.
          </p>

          <section>
            <h2>Coverage</h2>
            <CoverageLegend off={hiddenCoverage}
                            onToggle={(label) => setHiddenCoverage(
                              (was) => drop(was, label))} />
            <CoverageBars rows={stats.coverage} off={hiddenCoverage}
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
                    Each slot against one {stats.cost.base} pass, over the
                    parts the two share, every part at the newest seconds it
                    has -- most of them{' '}
                    <code>{stats.cost.build}</code>. A slot pools whatever
                    revisions drew it: held against
                    the same part, two revisions of a slot cost the same, and
                    reading a slot at one revision instead moves its ratio by
                    half with which parts that revision happened to draw.
                    Running all {stats.cost.slots.length} costs{' '}
                    {stats.cost.slots
                      .reduce((a, r) => a + (r.ratio ?? 0), 0).toFixed(1)}×
                    one {stats.cost.base} pass.
                    {elsewhere(stats.cost).map((row) => (
                      <span key={row.source}>
                        {' '}{ELSEWHERE} {row.source} spans{' '}
                        {row.revisions === 1 ? 'one revision'
                          : `${row.revisions} revisions`}, most of it{' '}
                        <code>{row.build}</code>.
                      </span>
                    ))}
                    {thin(stats.cost).length === 0 ? null : (
                      <span>
                        {' '}{THIN} {sentence(thin(stats.cost)
                          .map((row) => `${row.source} over `
                            + row.n.toLocaleString()))} of the{' '}
                        {stats.cost.n.toLocaleString()} parts, so those ratios
                        are not comparable with the rest: what a slot holds at
                        a revision is whatever was drawn into it last, and a
                        fill round draws the parts that failed before.
                      </span>
                    )}
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
            <PhaseLegend rows={stats.phases} off={hiddenPhases}
                         onToggle={(key) => setHiddenPhases(
                           (was) => drop(was, key))} />
            <PhaseBars rows={stats.phases} off={hiddenPhases} />
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
