import type { SidebarSelection } from '@pezlie/wall/src/Sidebar';
import type { WallViewState } from '@pezlie/wall/src/WallView';
import { DEFAULT_SHOWN, type Filter, type Sort } from '@lab/corpus/criteria';
import type { Grouping } from '@lab/corpus/facts';
import type { RampName, TintMode } from '@lab/corpus/tint';
import { readWallHash, readWallLink, wallHashString } from '@lab/corpus/wallHash';

/** The facet `CorpusWall`'s `excluded` list belongs to. */
const CATEGORY = 'category';

function defined<T extends object>(fields: T): Partial<T> {
  return Object.fromEntries(Object.entries(fields).filter(([, v]) => v !== undefined)) as Partial<T>;
}

/** `WallView`'s opening state from `CorpusWall`'s hash and hand-off link, so
 *  either wall's URL opens the other. A link outranks the hash field by field.
 *  The camera and caret are dropped: `WallView` takes neither. */
export function openingState(hash: string, search: string) {
  const h = readWallHash(hash);
  const link = readWallLink(search);
  const excluded = link.excluded ?? h.excluded;
  const selection: Partial<SidebarSelection> = defined({
    sort: h.sort,
    filter: link.filter ?? h.filter,
    shown: link.shown ? { ...DEFAULT_SHOWN, ...link.shown } : h.shown,
    grouping: h.grouping,
    tint: h.tint,
    gradient: h.gradient,
    desc: h.desc,
    exclude: excluded && { [CATEGORY]: excluded },
    tags: link.badges ?? h.badges,
  });
  return { ...defined({ slot: link.source ?? h.source, opened: h.part }), selection };
}

export function stateHash({ slot, opened, selection: s }: WallViewState): string {
  return wallHashString({
    source: slot,
    part: opened ?? undefined,
    sort: s.sort as Sort,
    filter: s.filter as Filter,
    shown: { ...DEFAULT_SHOWN, ...s.shown },
    grouping: s.grouping as Grouping,
    tint: s.tint as TintMode,
    gradient: s.gradient as RampName,
    desc: s.desc,
    excluded: [...(s.exclude?.[CATEGORY] ?? [])],
    badges: [...(s.tags ?? [])],
  });
}
