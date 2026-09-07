import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  clientToCanvas, fitViewToBounds, useCanvasSize, useViewAnimation, zoomAt, type View,
} from '@weasel-js/core';
import { LabShell } from '@weasel-js/labkit';
import type { LabClient } from '@lab/api/client';
import { clampWallView, DEFAULT_BLANK_PX } from '@lab/corpus/clamp';
import { categoryOf, COVERAGE_ORDER, groupers, rollUp } from '@lab/corpus/facts';
import { FilterBar } from '@lab/corpus/FilterBar';
import { bandedLayout, blockLayout } from '@lab/corpus/grouped';
import { gridLayout } from '@lab/corpus/layout';
import { Legend } from '@lab/corpus/Legend';
import { levelFor, pickLevel } from '@lab/corpus/levels';
import { Lightbox } from '@lab/corpus/Lightbox';
import type { CellState } from '@lab/corpus/palette';
import { PartCard } from '@lab/corpus/PartCard';
import { centerReveal } from '@lab/corpus/reveal';
import { applySelection, DEFAULT_SHOWN, type Selection } from '@lab/corpus/select';
import { Sidebar } from '@lab/corpus/Sidebar';
import { useCells } from '@lab/corpus/useCells';
import { useLooseThumbs } from '@lab/corpus/useLooseThumbs';
import { useParams } from '@lab/corpus/useParams';
import { useSheets, type Sheet } from '@lab/corpus/useSheets';
import { useVectorThumbs } from '@lab/corpus/useVectorThumbs';
import type { Cell } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
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

/** The whole app, minus its mount -- including labkit's `<LabShell>`, so this
 *  is a standalone lab and must not be nested inside a `<Lab>` or another
 *  `<LabShell>`. */
export function CorpusWall({ client }: { client: LabClient }) {
  const { params, setParam, reset: resetParams } = useParams();
  const [sources, setSources] = useState<{ source: string; n: number }[]>([]);
  const [source, setSource] = useState('census-naive');
  const fetched = useCells(client, source, params.pollMs);
  const loaded = useSheets(client, source);
  const [level, setLevel] = useState(32);
  const [selection, setSelection] = useState<Selection>({
    sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, grouping: 'none',
    tint: 'status', excluded: [], badges: [], desc: true,
  });
  const [cam, setCam] = useState<View | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
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
  const touched = useRef(false);
  const camInitialized = useRef(false);
  const camRef = useRef<View | null>(null);
  camRef.current = cam;
  const fittedGrouping = useRef<Selection['grouping']>('none');

  // The most-populated slot is the one worth opening on; the route already
  // orders them that way.
  useEffect(() => {
    void client.corpusSources().then(({ sources: got }) => {
      setSources(got);
      if (got[0]) setSource(got[0].source);
    }).catch(() => {});
  }, [client]);

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

  // Every camera write goes through this, so a flick's inertia decay -- which
  // calls `view.set` directly, bypassing any handler below -- gets clamped on
  // each intermediate frame too, not just once it comes to rest.
  const updateCam = (next: View) => {
    setCam(laid.bounds.w > 0 && size.width > 0 && size.height > 0
      ? clampWallView(next, laid.bounds, size, blankPx)
      : next);
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
  useEffect(() => {
    if (!cam) return;
    if (camInitialized.current) {
      setLevel((current) => pickLevel(current, params.cell * cam.scale.x,
                                       params.levelUpHysteresis, params.levelDownHysteresis));
    } else {
      camInitialized.current = true;
      setLevel(levelFor(params.cell * cam.scale.x));
    }
  }, [cam, params.cell, params.levelUpHysteresis, params.levelDownHysteresis]);

  const visible = useMemo(
    () => (cam ? visibleRange(laid.rects, cam, size) : []),
    [laid.rects, cam, size.width, size.height]);
  const loose = useLooseThumbs(shown, visible, level, drawnSource);
  const cellPx = cam ? params.cell * cam.scale.x : 0;
  const vector = useVectorThumbs(shown, visible, level, drawnSource, cellPx);

  // The 128 rung still draws from the 32px bake underneath -- a cell whose
  // loose image hasn't arrived yet needs something to show.
  const active = sheets[level === 8 ? 8 : 32] ?? null;

  // Stable across renders that don't touch these four -- `Wall`'s paint
  // effects key on this object, and a fresh one every render would repaint
  // every frame regardless of the camera.
  const appearance = useMemo(() => ({
    thickBorderFactor: params.thickBorderFactor, thinBorderFactor: params.thinBorderFactor,
    maxBorderPx: params.maxBorderPx, dimAlpha: params.dimAlpha,
    retiredWash: params.retiredWash,
    showBadges: params.showBadges, showCaptions: params.showCaptions,
  }), [params.thickBorderFactor, params.thinBorderFactor, params.maxBorderPx,
       params.dimAlpha, params.retiredWash, params.showBadges, params.showCaptions]);

  return (
    <LabShell title="brick-icons corpus"
              header={cells && (
                <>
                  <FilterBar sources={sources} source={source} onSource={setSource} />
                  <PartSearch client={client} onOpen={openSearchedPart} />
                  <button type="button" className="corpus-legend-toggle"
                          aria-pressed={legendOpen}
                          onClick={() => setLegendOpen((v) => !v)}>
                    Legend
                  </button>
                  {searchNotice && (
                    <span className="corpus-search-notice" role="status">{searchNotice}</span>
                  )}
                </>
              )}>
      <div className="corpus-app">
        {cells && (
          <Sidebar selection={selection} onChange={setSelection} counts={counts}
                   shown={shown.length} total={cells.length}
                   params={params} setParam={setParam} resetParams={resetParams} />
        )}
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
          {!cells && <p className="corpus-loading">loading the corpus…</p>}
          {cam && (
            <Wall cells={shown} rects={laid.rects} cam={cam}
                  sheet={active?.image ?? null} manifest={active?.manifest ?? null}
                  loose={loose} vector={vector} width={size.width} height={size.height}
                  highlight={highlight} highlightTag={highlightTag}
                  bands={laid.bands} tint={selection.tint}
                  explicitCaret={explicitCaret} onExplicitCaretChange={setExplicitCaret}
                  onPan={(next) => { touched.current = true; updateCam(next); }}
                  onPick={(c, at) => setCarded({ cell: c, at })}
                  onDragStart={() => setCarded(null)}
                  onOpen={(c) => { setCarded(null); setPicked(c.id); }}
                  dragThresholdPx={params.dragThresholdPx} appearance={appearance} />
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
