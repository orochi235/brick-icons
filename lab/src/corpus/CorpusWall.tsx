import { useEffect, useMemo, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { fitBounds, levelFor, pickLevel, zoomAt, type Camera } from '@lab/corpus/camera';
import { FilterBar } from '@lab/corpus/FilterBar';
import { gridLayout } from '@lab/corpus/layout';
import { Lightbox } from '@lab/corpus/Lightbox';
import { PartCard } from '@lab/corpus/PartCard';
import { applySelection, type Selection } from '@lab/corpus/select';
import { useCells } from '@lab/corpus/useCells';
import { useLooseThumbs } from '@lab/corpus/useLooseThumbs';
import { useSheets } from '@lab/corpus/useSheets';
import type { Cell } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
import { Wall } from '@lab/corpus/Wall';
import '@lab/corpus/corpus.css';

const CELL = 32;
const GAP = 4;

/** The whole app, minus its mount. Exported so a labkit instrument can host it
 *  without the standalone page. */
export function CorpusWall({ client }: { client: LabClient }) {
  const [sources, setSources] = useState<{ source: string; n: number }[]>([]);
  const [source, setSource] = useState('census-naive');
  const cells = useCells(client, source);
  const sheets = useSheets(client, source);
  const [level, setLevel] = useState(32);
  const [selection, setSelection] = useState<Selection>(
    { sort: 'id', filter: 'all' });
  const [cam, setCam] = useState<Camera | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [carded, setCarded] = useState<{ cell: Cell; at: { x: number; y: number } } | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });
  const touched = useRef(false);
  const camInitialized = useRef(false);

  // The most-populated slot is the one worth opening on; the route already
  // orders them that way.
  useEffect(() => {
    void client.corpusSources().then(({ sources: got }) => {
      setSources(got);
      if (got[0]) setSource(got[0].source);
    }).catch(() => {});
  }, [client]);

  // Reset to the middle rung on a slot change -- the old level belonged to
  // the previous corpus and camera.scale hasn't re-fired pickLevel yet.
  useEffect(() => { setLevel(32); }, [source]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ width: entry.contentRect.width,
                           height: entry.contentRect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [cells]);

  const shown = useMemo(
    () => (cells ? applySelection(cells, selection) : []),
    [cells, selection]);

  const cols = Math.max(1, Math.ceil(Math.sqrt(shown.length)));
  const laid = useMemo(
    () => gridLayout(shown, { cell: CELL, gap: GAP, cols }),
    [shown, cols]);

  useEffect(() => {
    if (touched.current || laid.bounds.w <= 0) return;
    setCam(fitBounds(laid.bounds, size));
  }, [laid.bounds, size]);

  // Hysteresis governs transitions, and the first pick has nothing to be
  // hysteretic about -- the camera's first fit sets the level directly, and
  // only later camera changes route through pickLevel.
  useEffect(() => {
    if (!cam) return;
    if (camInitialized.current) {
      setLevel((current) => pickLevel(current, CELL * cam.scale));
    } else {
      camInitialized.current = true;
      setLevel(levelFor(CELL * cam.scale));
    }
  }, [cam]);

  const visible = useMemo(
    () => (cam ? visibleRange(laid.rects, cam, size) : []),
    [laid.rects, cam, size]);
  const loose = useLooseThumbs(shown, visible, level, source);

  // The 128 rung still draws from the 32px bake underneath -- a cell whose
  // loose image hasn't arrived yet needs something to show.
  const active = sheets[level === 8 ? 8 : 32] ?? null;

  if (!cells) return <p className="corpus-loading">loading the corpus…</p>;

  return (
    <div className="corpus-app">
      <FilterBar selection={selection} onChange={setSelection}
                 shown={shown.length} total={cells.length}
                 sources={sources} source={source} onSource={setSource} />
      <div className="corpus-stage" ref={box}
           onWheel={(e) => {
             if (!cam) return;
             touched.current = true;
             const r = e.currentTarget.getBoundingClientRect();
             setCam(zoomAt(cam, e.clientX - r.left, e.clientY - r.top,
                           e.deltaY < 0 ? 1.1 : 1 / 1.1));
           }}>
        {cam && (
          <Wall cells={shown} rects={laid.rects} cam={cam}
                sheet={active?.image ?? null} manifest={active?.manifest ?? null}
                loose={loose} width={size.width} height={size.height}
                onPick={(c, at) => setCarded({ cell: c, at })}
                onOpen={(c) => { setCarded(null); setPicked(c.id); }} />
        )}
        {carded && !picked && (
          <PartCard cell={carded.cell} source={source} at={carded.at}
                    viewport={size}
                    onOpen={(id) => { setCarded(null); setPicked(id); }}
                    onClose={() => setCarded(null)} />
        )}
      </div>
      {picked && (
        <Lightbox partId={picked} source={source} client={client}
                  onClose={() => setPicked(null)} />
      )}
    </div>
  );
}
