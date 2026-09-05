import { useEffect, useMemo, useRef, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import { fitBounds, zoomAt, type Camera } from '@lab/corpus/camera';
import { FilterBar } from '@lab/corpus/FilterBar';
import { gridLayout } from '@lab/corpus/layout';
import { Lightbox } from '@lab/corpus/Lightbox';
import { applySelection, type Selection } from '@lab/corpus/select';
import { useCells } from '@lab/corpus/useCells';
import type { SheetManifest } from '@lab/corpus/types';
import { Wall } from '@lab/corpus/Wall';
import '@lab/corpus/corpus.css';

const SHEET_LEVEL = 32;
const CELL = 32;
const GAP = 4;

/** The whole app, minus its mount. Exported so a labkit instrument can host it
 *  without the standalone page. */
export function CorpusWall({ client }: { client: LabClient }) {
  const [sources, setSources] = useState<{ source: string; n: number }[]>([]);
  const [source, setSource] = useState('census-naive');
  const cells = useCells(client, source);
  const [manifest, setManifest] = useState<SheetManifest | null>(null);
  const [sheet, setSheet] = useState<HTMLImageElement | null>(null);
  const [selection, setSelection] = useState<Selection>(
    { sort: 'id', filter: 'all' });
  const [cam, setCam] = useState<Camera | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 600 });

  // The most-populated slot is the one worth opening on; the route already
  // orders them that way.
  useEffect(() => {
    void client.corpusSources().then(({ sources: got }) => {
      setSources(got);
      if (got[0]) setSource(got[0].source);
    }).catch(() => {});
  }, [client]);

  useEffect(() => {
    setSheet(null);
    void client.sheetManifest(source, SHEET_LEVEL).then(setManifest).catch(() => {});
    const img = new Image();
    img.onload = () => setSheet(img);
    img.src = `/api/thumbs/${source}/sheet-${SHEET_LEVEL}.png`;
  }, [client, source]);

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
    if (cam === null && laid.bounds.w > 0) setCam(fitBounds(laid.bounds, size));
  }, [cam, laid.bounds, size]);

  if (!cells) return <p className="corpus-loading">loading the corpus…</p>;

  return (
    <div className="corpus-app">
      <FilterBar selection={selection} onChange={setSelection}
                 shown={shown.length} total={cells.length}
                 sources={sources} source={source} onSource={setSource} />
      <div className="corpus-stage" ref={box}
           onWheel={(e) => {
             if (!cam) return;
             const r = e.currentTarget.getBoundingClientRect();
             setCam(zoomAt(cam, e.clientX - r.left, e.clientY - r.top,
                           e.deltaY < 0 ? 1.1 : 1 / 1.1));
           }}>
        {cam && (
          <Wall cells={shown} rects={laid.rects} cam={cam} sheet={sheet}
                manifest={manifest} width={size.width} height={size.height}
                onPick={(c) => setPicked(c.id)} />
        )}
      </div>
      {picked && (
        <Lightbox partId={picked} source={source} client={client}
                  onClose={() => setPicked(null)} />
      )}
    </div>
  );
}
