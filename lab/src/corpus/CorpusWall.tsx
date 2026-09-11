import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  clientToCanvas, fitViewToBounds, useCanvasSize, useViewAnimation, zoomAt, type View,
} from '@weasel-js/core';
import { LabShell } from '@weasel-js/labkit';
import { ToggleBar } from '@weasel-js/ui';
import type { LabClient } from '@lab/api/client';
import { clampWallView, DEFAULT_BLANK_PX, sameView } from '@lab/corpus/clamp';
import { readWallHash, wallHashString } from '@lab/corpus/wallHash';
import { categoryOf, COVERAGE_ORDER, groupers, rollUp } from '@lab/corpus/facts';
import { FilterBar } from '@lab/corpus/FilterBar';
import { bandedLayout, blockLayout } from '@lab/corpus/grouped';
import { gridLayout } from '@lab/corpus/layout';
import { Legend } from '@lab/corpus/Legend';
import { PAGES } from '@lab/nav/pages';
import { levelFor, pickLevel } from '@lab/corpus/levels';
import { Lightbox } from '@lab/corpus/Lightbox';
import type { CellState } from '@lab/corpus/palette';
import { PartCard } from '@lab/corpus/PartCard';
import { centerReveal } from '@lab/corpus/reveal';
import { DEFAULT_SHOWN } from '@lab/corpus/criteria';
import { applySelection, type Selection } from '@lab/corpus/select';
import { Sidebar } from '@lab/corpus/Sidebar';
import { useCells } from '@lab/corpus/useCells';
import { CacheFailureButton } from '@lab/corpus/CacheFailureButton';
import { cacheReport, probeCell } from '@lab/corpus/cacheReport';
import { useLooseThumbs, type LooseHandle } from '@lab/corpus/useLooseThumbs';
import { useParams } from '@lab/corpus/useParams';
import { SHEET_LEVELS, useSheets, type Sheet } from '@lab/corpus/useSheets';
import { useVectorThumbs, targetPxFor, vectorUrl, type VectorHandle }
  from '@lab/corpus/useVectorThumbs';
import type { Cell } from '@lab/corpus/types';
import { staleCount } from '@lab/corpus/sheet';
import { visibleRange } from '@lab/corpus/visible';
import { useVisualViewport } from '@lab/corpus/useVisualViewport';
import { Wall } from '@lab/corpus/Wall';
import { PartSearch } from '@lab/shared/PartSearch';
import '@lab/corpus/corpus.css';

const IDENTITY_VIEW: View = { x: 0, y: 0, scale: { x: 1, y: 1 } };

// Stable identity: a slot with nothing in it yet must not hand the memos
// below a fresh array on every render.
const NO_CELLS: Cell[] = [];

/** How much of the viewport's height a cell fills when the wall jumps to it.
 *  A jump that lands on a 32px cell has not really arrived. */
const JUMP_MIN_CELL_HEIGHT = 0.5;
// `blockLayout` takes no order for the groupings that have none of their own.
const NO_ORDER: string[] = [];

/** How far the canvas will follow a pinch before letting the compositor take
 *  over. The backing store costs the square of this. */
const MAX_PIXEL_SCALE = 3;

/** Slack around the pinched slice, as a fraction of it: a pinch-pan exposes
 *  new cells before its scroll event lands, and without the margin they arrive
 *  as blank ground. */
const SLICE_PAD = 0.25;

/** The whole app, minus its mount -- including labkit's `<LabShell>`, so this
 *  is a standalone lab and must not be nested inside a `<Lab>` or another
 *  `<LabShell>`. */
/** The wall's shape before its cells arrive.

 *  A cell's size is a parameter, not something the corpus tells us, so the
 *  grid can be drawn while the fetch is still out -- and everything around it
 *  (the slot picker, search, the sidebar) needs no cells either. Blocking on
 *  the whole corpus meant a blank page for as long as 24,591 rows take. */
function WallSkeleton({ cell, gap, width, height }: {
  cell: number; gap: number; width: number; height: number;
}) {
  const pitch = cell + gap;
  const cols = Math.max(1, Math.ceil((width || 800) / pitch));
  const rows = Math.max(1, Math.ceil((height || 600) / pitch));
  return (
    <div className="corpus-skeleton" aria-busy="true" role="status"
         style={{ gridTemplateColumns: `repeat(${cols}, ${cell}px)`, gap: `${gap}px` }}>
      <span className="corpus-skeleton__say">loading the corpus…</span>
      {Array.from({ length: cols * rows }, (_, i) => (
        <span key={i} className="corpus-skeleton__cell" style={{ height: `${cell}px` }} />
      ))}
    </div>
  );
}


/** The slot the wall opens on with nothing in the hash: the engine's own
 *  canonical drawing. Population picked this before, which meant `reference`
 *  -- LDView drew every part in the library, so the biggest slot is never
 *  ours. */
export const DEFAULT_SOURCE = 'occt';


export function CorpusWall({ client }: { client: LabClient }) {
  const { params, setParam, reset: resetParams } = useParams();
  // Read once, at the first render: restoring the slot through an effect would
  // fetch the default slot's cells before replacing them, and the sources poll
  // below would have already chosen for us.
  const fromHash = useRef(readWallHash(window.location.hash));
  const [sources, setSources] = useState<{ source: string; n: number }[]>([]);
  const [source, setSource] = useState(fromHash.current.source ?? DEFAULT_SOURCE);
  const fetched = useCells(client, source, params.pollMs);
  const loaded = useSheets(client, source);
  const [level, setLevel] = useState(32);
  const [selection, setSelection] = useState<Selection>({
    sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, grouping: 'none',
    tint: 'status', gradient: 'ember', excluded: [], badges: [], desc: true,
  });
  const [cam, setCam] = useState<View | null>(null);
  const [picked, setPicked] = useState<string | null>(fromHash.current.part ?? null);
  const [carded, setCarded] = useState<{ cell: Cell; at: { x: number; y: number } } | null>(null);
  const [highlight, setHighlight] = useState<CellState | null>(null);
  const [highlightTag, setHighlightTag] = useState<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  // A ref, not state: the wheel handler reads it in the same tick the pointer
  // moved, and a re-render per hover would repaint the wall.
  const overCard = useRef(false);
  const [explicitCaret, setExplicitCaret] = useState<number | null>(null);
  const [searchNotice, setSearchNotice] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const { width, height } = useCanvasSize(box);
  // Read rather than repeated in TypeScript: the panels set their own width
  // from this property, and the pan allowance has to be the same number.
  const [blankPx, setBlankPx] = useState(DEFAULT_BLANK_PX);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const declared = getComputedStyle(el).getPropertyValue('--corpus-panel-width').trim();
    const px = declared.endsWith('rem')
      ? parseFloat(declared) * parseFloat(getComputedStyle(document.documentElement).fontSize)
      : parseFloat(declared);
    if (Number.isFinite(px) && px > 0) setBlankPx(px);
  }, [width]);
  const size = { width, height };
  const vv = useVisualViewport();
  // Capped: the backing store grows with the square of this, and a pinch can
  // run well past any zoom worth drawing for. Beyond the cap the compositor
  // magnifies, which is what it did at every scale before.
  const pixelScale = Math.min(vv.scale, MAX_PIXEL_SCALE);
  // The slice of the stage a pinch has left on screen, in the stage's own CSS
  // pixels, padded so a pinch-pan has somewhere to go before the next scroll
  // event lands. Unpinched this is the whole stage and nothing changes.
  const slice = useMemo(() => {
    const el = box.current;
    if (!el || vv.scale <= 1) return { x: 0, y: 0, width, height };
    const r = el.getBoundingClientRect();
    const padX = vv.width * SLICE_PAD, padY = vv.height * SLICE_PAD;
    const x0 = Math.max(0, vv.left - r.left - padX);
    const y0 = Math.max(0, vv.top - r.top - padY);
    const x1 = Math.min(width, vv.left + vv.width - r.left + padX);
    const y1 = Math.min(height, vv.top + vv.height - r.top + padY);
    return { x: x0, y: y0,
             width: Math.max(0, x1 - x0), height: Math.max(0, y1 - y0) };
  }, [vv, width, height]);
  const touched = useRef(false);
  const camInitialized = useRef(false);
  const camRef = useRef<View | null>(null);
  camRef.current = cam;
  const fittedGrouping = useRef<Selection['grouping']>('none');

  // Polled, not fetched once: a slot appears when its renders are indexed, and
  // fetching at mount alone left a page open across an ingest showing a menu
  // that no longer matched the store, with nothing on screen saying so. A
  // later poll adds entries without moving anyone off what they are looking
  // at: a slot named in the hash is a choice already made, and so is the
  // default.
  const opened = useRef(!!fromHash.current.source);
  useEffect(() => {
    let live = true;
    const load = () => void client.corpusSources().then(({ sources: got }) => {
      if (!live) return;
      setSources(got);
      // The default stands wherever it has renders; population decides only
      // when it has none, so a store without an occt slot still opens on
      // something rather than on an empty wall.
      if (!opened.current && got[0]) {
        opened.current = true;
        if (!got.some((s) => s.source === DEFAULT_SOURCE)) setSource(got[0].source);
      }
    }).catch(() => {});
    load();
    const id = setInterval(load, params.pollMs);
    return () => { live = false; clearInterval(id); };
  }, [client, params.pollMs]);

  // What is on screen: the newest slot whose cells and sheets are both in
  // hand, which is the slot before this one until the new one has both.
  // Switching used to blank the wall for as long as that took, and pairing a
  // new `source` with old cells is what fires loose-thumb 404s -- so the
  // three travel together or not at all.
  const drawn = useRef<{ source: string; cells: Cell[];
                         sheets: Record<number, Sheet> } | null>(null);
  if (fetched.cells && fetched.source === loaded.source) {
    drawn.current = { source: fetched.source, cells: fetched.cells,
                      sheets: loaded.sheets };
  }
  const view = drawn.current;
  const cells = view?.cells ?? null;
  const all = cells ?? NO_CELLS;
  const sheets = view?.sheets ?? {};
  const drawnSource = view?.source ?? source;
  // The toolbar has moved and the cells have not caught up. Keeping the old
  // pictures beats blanking the wall, but only if the wall says they are the
  // old pictures -- unsaid, a slot change reads as "this slot looks identical".
  const stale = view != null && drawnSource !== source;

  const shown = useMemo(
    () => (cells ? applySelection(cells, selection) : []),
    [cells, selection]);

  // The wall as it would be with no tag picked. The legend's tag rows count
  // over this rather than over `shown`, because they are the control that
  // applies the picks: counted over `shown`, picking `technic` reads every
  // other tag as 0 and the menu stops saying where you could go next.
  const untagged = useMemo(
    () => (cells ? (selection.badges.length === 0
                    ? shown
                    : applySelection(cells, { ...selection, badges: [] }))
                 : []),
    [cells, selection, shown]);

  // Counted over the whole slot, not over `shown` -- a facet's own checkbox
  // must not zero out the moment it is cleared.
  const counts = useMemo(() => {
    const out = new Map<string, number>();
    for (const c of all) {
      const name = categoryOf(c);
      out.set(name, (out.get(name) ?? 0) + 1);
    }
    return out;
  }, [all]);

  const rolled = useMemo(() => rollUp(shown), [shown]);

  const layout = useMemo(() => {
    const keys = groupers(selection.grouping, rolled);
    if (keys.length === 0) return gridLayout;
    if (keys.length === 1) {
      return blockLayout(keys[0]!, selection.grouping === 'coverage'
                                     ? COVERAGE_ORDER : NO_ORDER);
    }
    return bandedLayout(keys[0]!, keys[1]!, selection.desc);
  }, [selection.grouping, selection.desc, rolled]);

  // 0 means auto -- the override exists for judging a fixed grid shape, not
  // for replacing the default that already fills the wall's width.
  const cols = params.cols > 0 ? params.cols : Math.max(1, Math.ceil(Math.sqrt(shown.length)));
  const laid = useMemo(
    () => layout(shown, { cell: params.cell, gap: params.gap, cols }),
    [layout, shown, cols, params.cell, params.gap]);
  const pitch = params.cell + params.gap;

  // Written on every change, not on unload: a reload is not the only way back
  // here, and a link someone copies mid-session has to carry what they can see.
  // `replaceState`, so the browser's Back button still leaves the wall rather
  // than walking through every part that has been opened.
  useEffect(() => {
    const next = wallHashString({ source, part: picked ?? undefined });
    if (next !== window.location.hash) {
      window.history.replaceState(null, '', next || window.location.pathname);
    }
  }, [source, picked]);

  // Every camera write goes through this, so a flick's inertia decay -- which
  // calls `view.set` directly, bypassing any handler below -- gets clamped on
  // each intermediate frame too, not just once it comes to rest.
  const updateCam = (next: View) => {
    const clamped = laid.bounds.w > 0 && size.width > 0 && size.height > 0
      ? clampWallView(next, laid.bounds, size, blankPx)
      : next;
    // By value, not by reference. `clampView` hands back its argument when
    // nothing is out of bounds but builds a fresh object the moment it clamps,
    // so a camera pinned against an edge produced a new one on every pointer
    // event while its four numbers stood still -- a re-render that changed
    // nothing, and a write that could re-enter itself without end.
    setCam((current) => (sameView(current, clamped) ? current : clamped));
  };

  // Glides rather than jumps -- reads the live camera through the ref, so an
  // animation started mid-drag or mid-decay resumes from where the camera
  // actually is rather than a captured value.
  const camAnim = useViewAnimation({ get: () => camRef.current ?? IDENTITY_VIEW, set: updateCam });

  // A search hit may not be on the wall at all: `/api/parts` runs over the
  // whole LDraw index, so it can name a part this source never drew, or one
  // the current filter is hiding. Either way, say so instead of flying to a
  // cell that isn't there or doing nothing silently.
  const openSearchedPart = (partId: string) => {
    const index = shown.findIndex((c) => c.id === partId);
    if (index < 0) {
      const known = cells?.some((c) => c.id === partId) ?? false;
      setSearchNotice(known
        ? `${partId} is hidden by the current filter`
        : `${partId} is not drawn in this slot`);
      return;
    }
    setSearchNotice(null);
    const rect = laid.rects[index];
    if (rect && cam) {
      touched.current = true;
      camAnim.animate(centerReveal(rect, cam, size, JUMP_MIN_CELL_HEIGHT));
    }
    setExplicitCaret(index);
    setCarded({ cell: shown[index]!, at: { x: size.width / 2, y: size.height / 2 } });
  };

  // Fits the wall's width into the viewport and lets it run off the bottom,
  // rather than shrinking to fit both axes -- 'fill' picks whichever axis's
  // ratio is larger, which for a viewport wider than the wall is width's.
  // The wall's own top-left belongs at the viewport's top-left, so only the
  // scale from the fit is kept; centering the bounds would crop row zero.
  // A regroup moves every cell and so changes `laid.bounds`, but it is not a
  // reason to re-fit: the reader asked for a different arrangement, not for
  // their camera back at the top. The sync below runs after this effect, so
  // within the commit that changes the grouping this still sees the old one.
  const fitToWall = useCallback(() => {
    if (laid.bounds.w <= 0 || size.width <= 0 || size.height <= 0) return;
    const fitted = fitViewToBounds(
      { x: 0, y: 0, width: laid.bounds.w, height: laid.bounds.h },
      size, camRef.current ?? IDENTITY_VIEW, { mode: 'fill', padding: 0 });
    updateCam({ x: 0, y: 0, scale: fitted.scale });
  }, [laid.bounds.w, laid.bounds.h, size.width, size.height]);

  useEffect(() => {
    if (fittedGrouping.current !== selection.grouping) return;
    if (touched.current) return;
    fitToWall();
  }, [laid.bounds.w, laid.bounds.h, size.width, size.height]);

  // cmd-0 puts the whole wall back on screen, the way it opened. Also clears
  // `touched`, so a later resize refits rather than holding the camera the
  // reset just replaced.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '0' || !(e.metaKey || e.ctrlKey) || e.altKey) return;
      e.preventDefault();
      touched.current = false;
      // Also the zoom level, not just the camera: leaving `camInitialized` set
      // sends the refit through pickLevel's hysteresis, which holds whatever
      // rung the last camera move reached. Clearing it takes the direct
      // `levelFor` branch -- the same one the wall opens on.
      camInitialized.current = false;
      fitToWall();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [fitToWall]);

  useEffect(() => { fittedGrouping.current = selection.grouping; },
            [selection.grouping]);

  // The only thing that sets the level: a slot change must not touch it, or
  // the wall sits on the 32px sheet until the next camera move.
  // Hysteresis governs transitions, and the first pick has nothing to be
  // hysteretic about -- the camera's first fit sets the level directly, and
  // only later camera changes route through pickLevel.
  //
  // On the drawn cell size and the viewport, NOT on the camera object. A
  // camera held against a bound is rewritten on every pointer event -- the
  // clamp builds a new object whenever it clamps anything -- and keying this
  // to `cam` meant every one of those writes re-picked a level that could not
  // have changed. The viewport is here in its own right: a resize re-fits, and
  // the fit is what the level is read off.
  // Multiplied by the pinch: this is the size a cell is actually drawn at on
  // the glass, which is the only thing a mip level should be read off.
  const cellPx = cam ? params.cell * cam.scale.x * pixelScale : 0;
  useEffect(() => {
    if (!cam) return;
    if (camInitialized.current) {
      setLevel((current) => pickLevel(current, cellPx,
                                       params.levelUpHysteresis, params.levelDownHysteresis));
    } else {
      camInitialized.current = true;
      setLevel(levelFor(cellPx));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cellPx, size.width, size.height,
      params.levelUpHysteresis, params.levelDownHysteresis]);

  const visible = useMemo(
    () => (cam ? visibleRange(laid.rects, cam, slice) : []),
    [laid.rects, cam, slice]);
  // The two upper rungs' read-and-reset handles, for the header's cache
  // report. Both rungs swallow their own failures on purpose, so this is the
  // only way to ask them what happened.
  const looseHandle = useRef<LooseHandle | null>(null);
  const vectorHandle = useRef<VectorHandle | null>(null);
  const loose = useLooseThumbs(shown, visible, level, drawnSource, looseHandle);
  const vector = useVectorThumbs(shown, visible, level, drawnSource, cellPx,
                                 vectorHandle);

  const gatherCacheReport = async () => {
    const dpr = window.devicePixelRatio || 1;
    const targetPx = targetPxFor(cellPx, dpr);
    const seen = visible.map((i) => shown[i]).filter((c) => c !== undefined);
    // Three, not one: a single 404 is a part with no render, and the same
    // answer on three says the rung is broken rather than the part.
    const probes = await Promise.all(
      seen.filter((c) => c!.sha).slice(0, 3).map(
        (c) => probeCell(c!.id, vectorUrl(c!, drawnSource), targetPx)));
    return cacheReport({
      slot: drawnSource,
      cellPx, dpr, level,
      cells: {
        shown: shown.length,
        visible: seen.length,
        visibleWithSha: seen.filter((c) => c!.sha).length,
      },
      sheets: SHEET_LEVELS.map((lvl) => {
        const sheet = sheets[lvl];
        return {
          level: lvl,
          loaded: sheet !== undefined,
          version: sheet?.manifest.version ?? null,
          baked: sheet ? Object.keys(sheet.manifest.baked).length : 0,
        };
      }),
      loose: looseHandle.current?.stats() ?? { loaded: 0, requested: 0 },
      vector: vectorHandle.current?.stats()
        ?? { resident: 0, inFlight: 0, queued: 0, bytesCached: 0, rasterPx: [] },
      probes,
    });
  };

  // The 128 rung still draws from the 32px bake underneath -- a cell whose
  // loose image hasn't arrived yet needs something to show.
  const active = sheets[level === 8 ? 8 : 32] ?? null;

  // A slot whose sheet disagrees with the store on most of its cells is a
  // bake that did not finish or a re-encode that moved every sha. The wall
  // draws the stale tiles anyway, so without this the only symptom is that
  // the pictures are quietly out of date.
  const reported = useRef<string>('');
  useEffect(() => {
    if (!active?.manifest || !shown.length) return;
    const key = `${drawnSource}:${active.manifest.level}`;
    if (reported.current === key) return;
    reported.current = key;
    const { stale, missing, total } = staleCount(active.manifest, shown);
    if (stale + missing > total / 10) {
      console.warn(`[corpus] ${drawnSource} sheet-${active.manifest.level}: `
        + `${stale} of ${total} cells stale, ${missing} with no tile. `
        + `Re-run scripts/bake-thumbs.py.`);
    }
  }, [active, shown, drawnSource]);

  // Stable across renders that don't touch these four -- `Wall`'s paint
  // effects key on this object, and a fresh one every render would repaint
  // every frame regardless of the camera.
  const appearance = useMemo(() => ({
    thickBorderFactor: params.thickBorderFactor, thinBorderFactor: params.thinBorderFactor,
    maxBorderPx: params.maxBorderPx, dimAlpha: params.dimAlpha,
    retiredWash: params.retiredWash,
    showBadges: params.showBadges, showCaptions: params.showCaptions,
    washRetired: params.washRetired,
  }), [params.thickBorderFactor, params.thinBorderFactor, params.maxBorderPx,
       params.dimAlpha, params.retiredWash, params.showBadges, params.showCaptions,
       params.washRetired]);

  return (
    <LabShell title="brick-icons corpus" pages={PAGES}
              header={(
                <>
                  <FilterBar sources={sources} source={source} onSource={setSource} />
                  <PartSearch client={client} onOpen={openSearchedPart} />
                  {/* A one-item ToggleBar rather than a Button: this
                      reports a state, and `aria-pressed` is what says so.
                      Button grew a `pressed` prop for exactly this, but not
                      until @weasel-js/ui 1.4.1 -- the lab is on 1.4.0.
                      `lab-nav-alike` gives it the page nav's segmented look:
                      the two sit side by side and both are places to be. */}
                  <ToggleBar mode="multiple" size="sm" variant="minimal"
                             ariaLabel="Panels" className="lab-nav-alike"
                             items={[{ value: 'legend', label: 'Legend' }]}
                             value={legendOpen ? ['legend'] : []}
                             onChange={(v) => setLegendOpen(v.includes('legend'))} />
                  <CacheFailureButton
                    report={gatherCacheReport}
                    reset={() => {
                      looseHandle.current?.reset();
                      vectorHandle.current?.reset();
                    }} />
                  {searchNotice && (
                    <span className="corpus-search-notice" role="status">{searchNotice}</span>
                  )}
                </>
              )}>
      <div className="corpus-app">
        <Sidebar selection={selection} onChange={setSelection} counts={counts}
                 shown={shown.length} total={all.length}
                 params={params} setParam={setParam} resetParams={resetParams} />
        {/* `useCanvasSize` measures the stage once, on its own first mount --
            it has to exist from the start, not appear once cells arrive. */}
        <div className="corpus-stage" ref={box}
             onWheel={(e) => {
               if (!cam) return;
               touched.current = true;
               const [sx, sy] = clientToCanvas(e.currentTarget, e.clientX, e.clientY);
               // The card is anchored to a screen point, and a zoom moves the
               // cell out from under it -- so a zoom drops it, unless it is
               // the card being read: the pointer is over it and has not left.
               if (!overCard.current) setCarded(null);
               updateCam(zoomAt(cam, { x: sx, y: sy }, e.deltaY < 0 ? 1.1 : 1 / 1.1));
             }}>
          {!cells && <WallSkeleton cell={params.cell} gap={params.gap}
                                   width={size.width} height={size.height} />}
          {cam && (
            <Wall cells={shown} rects={laid.rects} cam={cam}
                  sheet={active?.image ?? null} manifest={active?.manifest ?? null}
                  loose={loose} vector={vector} width={size.width} height={size.height}
                  highlight={highlight} highlightTag={highlightTag}
                  bands={laid.bands} tint={selection.tint}
                  gradient={selection.gradient}
                  explicitCaret={explicitCaret} onExplicitCaretChange={setExplicitCaret}
                  onPan={(next) => { touched.current = true; updateCam(next); }}
                  onPick={(c, at) => setCarded({ cell: c, at })}
                  onDragStart={() => setCarded(null)}
                  onOpen={(c) => { setCarded(null); setPicked(c.id); }}
                  dragThresholdPx={params.dragThresholdPx} appearance={appearance}
                  stale={stale}
                  pixelScale={pixelScale} sceneRenderer={params.sceneRenderer} />
          )}
          {stale && (
            <p className="corpus-stale" role="status">
              still showing <b>{drawnSource}</b> while <b>{source}</b> loads
            </p>
          )}
          {carded && !picked && (
            <PartCard cell={carded.cell} source={drawnSource} at={carded.at}
                      viewport={size}
                      onOpen={(id) => { setCarded(null); setPicked(id); }}
                      onClose={() => setCarded(null)}
                      onHoverChange={(over) => { overCard.current = over; }} />
          )}
          {cells && legendOpen && (
            <Legend cells={shown} tagCells={untagged}
                    highlight={highlight} onHighlight={setHighlight}
                    badges={selection.badges}
                    onBadges={(update) => setSelection((s) => ({ ...s, badges: update(s.badges) }))}
                    highlightTag={highlightTag} onHighlightTag={setHighlightTag}
                    onClose={() => setLegendOpen(false)} />
          )}
        </div>
        {picked && (
          <Lightbox partId={picked} source={drawnSource} client={client}
                    onClose={() => setPicked(null)} />
        )}
      </div>
    </LabShell>
  );
}
