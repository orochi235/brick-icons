import { useCallback, useEffect, useMemo } from 'react';
import { defaultUrls } from '@castleblack/wall/src/urls';
import { WallView, type WallViewState } from '@castleblack/wall/src/WallView';
import type { LabClient } from '@lab/api/client';
import { DEFAULT_SOURCE } from '@lab/corpus/CorpusWall';
import { drawSticker } from '@lab/corpus/draw2d';
import { familyOf } from '@lab/corpus/families';
import { Lightbox } from '@lab/corpus/Lightbox';
import { LINKED_BADGE, RETIRED_WASH, thumbGround } from '@lab/corpus/paint';
import { PartCardBody } from '@lab/corpus/PartCard';
import type { TintMode } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';
import { WALL_LINK_PARAMS } from '@lab/corpus/wallHash';
import { PAGES } from '@lab/nav/pages';
import { openingState, stateHash } from '@lab/wall/hash';
import { GROUPINGS, SPEC } from '@lab/wall/host';

const URLS = defaultUrls('/api');
const LINKED = [LINKED_BADGE];
const FACET = { key: 'category', label: 'category', groupOf: familyOf };

const drawMark = (ctx: CanvasRenderingContext2D, _mark: string, cx: number, cy: number,
                  r: number) => drawSticker(ctx, cx, cy, r);
const linkTarget = (cell: Cell, tag: string) =>
  (tag === LINKED_BADGE ? cell.successor ?? null : null);

/** The corpus wall drawn by castleblack's `WallView`, beside `CorpusWall`. */
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
  const onChange = useCallback((state: WallViewState) => {
    const next = stateHash(state);
    if (next !== window.location.hash) {
      window.history.replaceState(null, '', next || window.location.pathname);
    }
  }, []);

  return (
    <WallView title="brick-icons wall" pages={PAGES} spec={SPEC} urls={URLS}
              fetchItems={fetchItems} fetchSlots={fetchSlots} defaultSlot={DEFAULT_SOURCE}
              storageKey="brick-icons.wall-view.params" groupings={GROUPINGS} facet={FACET}
              initial={initial} onChange={onChange}
              renderCard={(cell, slot, card) => (
                <PartCardBody cell={cell} source={slot} tint={card.tint as TintMode}
                              onOpen={card.open} />
              )}
              renderDetail={(cell, slot, close) => (
                <Lightbox partId={cell.id} source={slot} client={client} onClose={close} />
              )}
              linkedBadges={LINKED} linkTarget={linkTarget}
              drawMark={drawMark} washColor={RETIRED_WASH} ground={thumbGround()} />
  );
}
