import { CLASS_SPECS, DEFAULT_SHOWN, type CellClass, type Shown }
  from '@lab/corpus/criteria';
import { wallLinkQuery } from '@lab/corpus/wallHash';

/** Which parts the tallies are about. The membership half of the wall's
 *  `Selection` and nothing else: `sort`, `grouping` and `tint` change how the
 *  wall draws, not which parts are in. */
export interface WorkingSet {
  /** One class of part, or all of them. The wall's `rendered` / `unrendered`
   *  / `errors` are absent on purpose -- each is a statement about a single
   *  slot, and the coverage chart already breaks every slot out that way. */
  kind: 'all' | 'printed' | 'obsolete' | 'base';
  /** Whether each of the wall's classes is in the set at all, which is not
   *  what `kind` asks: `kind: 'obsolete'` looks at nothing else. */
  shown: Shown;
  /** Clean category names left out entirely. */
  excluded: string[];
  /** Badge tags a part must carry -- every one of them, as on the wall. */
  badges: string[];
}

export const DEFAULT_SET: WorkingSet = {
  kind: 'all',
  // Obsolete parts are off here though the wall shows them: no batch renders
  // a superseded mould, so counting them made every slot look thousands of
  // parts short of done. `stats.CLASSES` holds the same defaults.
  shown: { ...DEFAULT_SHOWN, obsolete: false },
  excluded: [], badges: [],
};

const KINDS = new Set(['all', 'printed', 'obsolete', 'base']);

const CLASS_KEYS = new Set<string>(CLASS_SPECS.map((c) => c.key));

/** The query the API takes, which is also what goes in the address bar: one
 *  spelling, so a link and a request cannot describe different sets. A class
 *  is named only where it departs from the default -- `show=moved`,
 *  `hide=posed`. */
export function toQuery(set: WorkingSet): URLSearchParams {
  const q = new URLSearchParams();
  if (set.kind !== DEFAULT_SET.kind) q.set('kind', set.kind);
  for (const { key } of CLASS_SPECS) {
    if (set.shown[key] !== DEFAULT_SET.shown[key]) {
      q.append(set.shown[key] ? 'show' : 'hide', key);
    }
  }
  for (const name of set.excluded) q.append('excluded', name);
  for (const tag of set.badges) q.append('badges', tag);
  return q;
}

export function fromQuery(q: URLSearchParams): WorkingSet {
  const kind = q.get('kind');
  const shown = { ...DEFAULT_SET.shown };
  for (const [param, value] of [['show', true], ['hide', false]] as const) {
    for (const key of q.getAll(param)) {
      if (CLASS_KEYS.has(key)) shown[key as CellClass] = value;
    }
  }
  return {
    kind: kind && KINDS.has(kind) ? kind as WorkingSet['kind'] : 'all',
    shown,
    excluded: q.getAll('excluded'),
    badges: q.getAll('badges'),
  };
}

/** The wall showing the same parts, in the link the wall reads. */
export function wallHref(set: WorkingSet, source: string): string {
  const q = wallLinkQuery({
    source, filter: set.kind, shown: set.shown,
    excluded: set.excluded, badges: set.badges,
  });
  return `/corpus?${q}`;
}
