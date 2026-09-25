import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { defaultUrls } from '@pezlie/wall/src/urls';
import { WallView, type WallHeader, type WallViewState } from '@pezlie/wall/src/WallView';
import type { LabClient } from '@lab/api/client';
import type { LdrawColor } from '@lab/api/types';
import { ColorField, loadColors } from '@lab/config/ColorRow';
import { resolveHex } from '@lab/config/colorMatch';
import '@lab/corpus/corpus.css';
import { drawSticker } from '@lab/corpus/draw2d';
import { familyOf } from '@lab/corpus/families';
import { FilterBar } from '@lab/corpus/FilterBar';
import { Lightbox } from '@lab/corpus/Lightbox';
import { linkedPart, LINKED_BADGE, REPLACES_BADGE, RETIRED_WASH,
  thumbGround } from '@lab/corpus/paint';
import { PartCardBody } from '@lab/corpus/PartCard';
import type { TintMode } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';
import { DEFAULT_SOURCE, WALL_LINK_PARAMS } from '@lab/corpus/wallHash';
import { PAGES } from '@lab/nav/pages';
import { PartSearch } from '@lab/shared/PartSearch';
import '@lab/wall/BrickWall.css';
import { shadeFilter, useInk } from '@lab/wall/ink';
import { openingState, stateHash } from '@lab/wall/hash';
import { GROUPINGS, SPEC } from '@lab/wall/host';
import { searchNotice } from '@lab/wall/searchNotice';

const URLS = defaultUrls('/api');
const LINKED = [LINKED_BADGE, REPLACES_BADGE];
const FACET = { key: 'category', label: 'category', groupOf: familyOf };

const drawMark = (ctx: CanvasRenderingContext2D, _mark: string, cx: number, cy: number,
                  r: number) => drawSticker(ctx, cx, cy, r);
export const linkTarget = linkedPart;

/** The corpus wall drawn by pezlie's `WallView`, beside `CorpusWall`. */
export function BrickWall({ client }: { client: LabClient }) {
  const initial = useMemo(() => openingState(window.location.hash, window.location.search), []);
  // A link is a hand-off: left in the bar, a reload would put back a selection
  // the reader has since changed.
  useEffect(() => {
    const url = new URL(window.location.href);
    const had = WALL_LINK_PARAMS.filter((name) => url.searchParams.has(name));
    if (had.length === 0) return;
    for (const name of had) url.searchParams.delete(name);
    window.history.replaceState(null, '', url);
  }, []);

  const fetchItems = useCallback(async (slot: string, since?: string) => {
    const body = await client.cells(slot, since);
    return { items: body.cells, version: body.version };
  }, [client]);
  const fetchSlots = useCallback(async () => {
    const { sources } = await client.corpusSources();
    return sources.map(({ source, n }) => ({ slot: source, n }));
  }, [client]);
  const [notice, setNotice] = useState<string | null>(null);
  const [ink, setInk] = useInk();
  const [palette, setPalette] = useState<LdrawColor[]>([]);
  useEffect(() => { void loadColors(client).then(setPalette); }, [client]);
  const inkHex = useMemo(() => resolveHex(palette, ink), [palette, ink]);
  const imageFilter = useMemo(() => (inkHex ? shadeFilter(inkHex) : null), [inkHex]);
  // A slot change makes the last search's notice stale.
  const lastSlot = useRef<string | null>(null);
  const onChange = useCallback((state: WallViewState) => {
    if (lastSlot.current !== null && state.slot !== lastSlot.current) setNotice(null);
    lastSlot.current = state.slot;
    const next = stateHash(state);
    if (next !== window.location.hash) {
      window.history.replaceState(null, '', next || window.location.pathname);
    }
  }, []);

  // The header is the only thing handed `reveal`, and the card and lightbox
  // need it to follow a part link, so the latest one is kept here.
  const wall = useRef<WallHeader | null>(null);
  const header = useCallback((state: WallHeader) => {
    wall.current = state;
    return (
      <>
        <FilterBar sources={state.slots.map(({ slot, n }) => ({ source: slot, n }))}
                   source={state.slot} onSource={state.setSlot} />
        <span className="brick-wall-search">
          <PartSearch client={client}
                      onOpen={(partId) => setNotice(searchNotice(partId, state.reveal(partId)))} />
          <span className="corpus-search-notice" role="status">{notice ?? ''}</span>
        </span>
        <span className="brick-wall-ink" title="draw every part in one LEGO color">
          <ColorField client={client} label="" value={ink} onChange={setInk} />
        </span>
      </>
    );
  }, [client, notice, ink, setInk]);
  const goToPart = useCallback((partId: string) => {
    // No wall to ask is not a part that is missing from it, so it earns no
    // notice of its own.
    if (!wall.current) { setNotice(null); return; }
    setNotice(searchNotice(partId, wall.current.reveal(partId)));
  }, []);

  return (
    <WallView title="brick-icons wall" pages={PAGES} spec={SPEC} urls={URLS}
              fetchItems={fetchItems} fetchSlots={fetchSlots} defaultSlot={DEFAULT_SOURCE}
              storageKey="brick-icons.wall-view.params" groupings={GROUPINGS} facet={FACET}
              initial={initial} onChange={onChange}
              slotPicker={false} header={header}
              imageFilter={imageFilter}
              renderCard={(cell, slot, card) => (
                <PartCardBody cell={cell} source={slot} tint={card.tint as TintMode}
                              onOpen={card.open} onPart={goToPart} thumbFilter={imageFilter} />
              )}
              renderDetail={(cell, slot, close) => (
                <Lightbox partId={cell.id} source={slot} client={client} onClose={close}
                          successor={cell.successor} predecessors={cell.predecessors}
                          onPart={(partId) => { close(); goToPart(partId); }} />
              )}
              linkedBadges={LINKED} linkTarget={linkTarget}
              cssRoot="--corpus"
              drawMark={drawMark} washColor={RETIRED_WASH} ground={thumbGround()} />
  );
}
