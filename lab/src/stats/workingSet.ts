/** Which parts the tallies are about. The membership half of the wall's
 *  `Selection` and nothing else: `sort`, `grouping` and `tint` change how the
 *  wall draws, not which parts are in. */
export interface WorkingSet {
  /** One class of part, or all of them. The wall's `rendered` / `unrendered`
   *  / `errors` are absent on purpose -- each is a statement about a single
   *  slot, and the coverage chart already breaks every slot out that way. */
  kind: 'all' | 'printed' | 'obsolete' | 'base';
  /** `~Moved to` redirects, which are not parts anyone can draw. */
  moved: boolean;
  outOfScope: boolean;
  /** Clean category names left out entirely. */
  excluded: string[];
  /** Badge tags a part must carry -- every one of them, as on the wall. */
  badges: string[];
}

export const DEFAULT_SET: WorkingSet = {
  kind: 'all', moved: false, outOfScope: true, excluded: [], badges: [],
};

const KINDS = new Set(['all', 'printed', 'obsolete', 'base']);

/** The query the API takes, which is also what goes in the address bar: one
 *  spelling, so a link and a request cannot describe different sets. */
export function toQuery(set: WorkingSet): URLSearchParams {
  const q = new URLSearchParams();
  if (set.kind !== DEFAULT_SET.kind) q.set('kind', set.kind);
  if (set.moved !== DEFAULT_SET.moved) q.set('moved', String(set.moved));
  if (set.outOfScope !== DEFAULT_SET.outOfScope) {
    q.set('out_of_scope', String(set.outOfScope));
  }
  for (const name of set.excluded) q.append('excluded', name);
  for (const tag of set.badges) q.append('badges', tag);
  return q;
}

export function fromQuery(q: URLSearchParams): WorkingSet {
  const kind = q.get('kind');
  return {
    kind: kind && KINDS.has(kind) ? kind as WorkingSet['kind'] : 'all',
    moved: q.get('moved') === 'true',
    outOfScope: q.get('out_of_scope') !== 'false',
    excluded: q.getAll('excluded'),
    badges: q.getAll('badges'),
  };
}

/** The wall showing the same parts. Its own vocabulary differs -- it says
 *  `shown` where this says `moved` and `outOfScope`, and it needs a slot --
 *  so the translation happens here rather than in the markup. */
export function wallHref(set: WorkingSet, source: string): string {
  const q = new URLSearchParams({ source });
  if (set.kind !== 'all') q.set('filter', set.kind);
  if (set.moved) q.set('moved', 'true');
  if (!set.outOfScope) q.set('outOfScope', 'false');
  for (const name of set.excluded) q.append('excluded', name);
  for (const tag of set.badges) q.append('badges', tag);
  return `/corpus?${q}`;
}
