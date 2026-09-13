import { CLASS_SPECS, classKeys, DEFAULT_SHOWN, filterKeys, sortKeys,
         type Filter, type Shown, type Sort } from '@lab/corpus/criteria';
import { GROUPING_KEYS, type Grouping } from '@lab/corpus/facts';
import { decodeHashJson, encodeHashJson } from '@lab/corpus/hashCodec';
import { RAMP_NAMES, TINT_MODES, type RampName, type TintMode }
  from '@lab/corpus/tint';

/** What the corpus wall keeps in its URL, so a reload lands where you were.
 *
 *  The lightbox is the reason this exists: it is a whole page's worth of a
 *  part, reached by finding the cell, and a refresh used to close it with
 *  nothing saying which part had been open. `source` rides along because the
 *  lightbox draws from a slot, and the slot is otherwise chosen for you by the
 *  first sources poll -- restoring the part without it reopens the right part
 *  against the wrong renders.
 *
 *  The hash, not the query: `?part=` on the lab's own page is a hand-off that
 *  is consumed once and dropped, and these two mean the opposite thing.
 */
export interface WallHash {
  /** The part whose lightbox is open. */
  part?: string;
  /** The render slot the wall is drawing. */
  source?: string;
  /** The camera, once the reader has moved it. An untouched wall is left out,
   *  so a reload re-fits to the window it reloads into. */
  cam?: WallCam;
  /** The part the keyboard caret is on -- by id, because an index moves
   *  whenever a poll adds a cell ahead of it. */
  caret?: string;
  sort?: Sort;
  filter?: Filter;
  shown?: Shown;
  grouping?: Grouping;
  /** What the cells are colored by. Here because a wall tinted by render
   *  seconds is a different picture of the corpus, not a view setting: a
   *  link to it that arrives colored by status shows the reader something
   *  else and says nothing about it. */
  tint?: TintMode;
  /** The ramp a measured tint draws in. Only meaningful alongside one. */
  gradient?: RampName;
  desc?: boolean;
  excluded?: string[];
  badges?: string[];
}

export interface WallCam { x: number; y: number; scale: number }

/** Readable key to its condensed one. */
const KEYS = {
  source: 's', part: 'p', cam: 'c', caret: 'k', sort: 'o', filter: 'f',
  shown: 'v', group: 'g', tint: 't', gradient: 'r', desc: 'd', excl: 'x',
  badges: 'b',
} as const;
type Key = keyof typeof KEYS;

/** `excluded` and `badges` are only ever compared, never rendered or used as
 *  a path, so they stay opaque -- but not unbounded. */
const LIST_MAX = 64;
const ITEM_MAX = 80;

/** Closed vocabularies, so these are checked against their own lists rather
 *  than the shape below: an unknown mode is not a harmless string to pass on,
 *  it is a wall colored by nothing. */
function known<T extends string>(allowed: readonly T[], value: string | null):
    T | undefined {
  return value !== null && (allowed as readonly string[]).includes(value)
    ? value as T : undefined;
}

/** A slot name or part id, and nothing that could be read as markup or a
 *  path. Anything else in the hash was not written by us. */
const SAFE = /^[A-Za-z0-9][A-Za-z0-9._~-]{0,79}$/;

function clean(value: string | null): string | undefined {
  return value && SAFE.test(value) ? value : undefined;
}

function readCam(value: string | null): WallCam | undefined {
  const parts = value?.split(',').map(Number);
  if (!parts || parts.length !== 3 || !parts.every(Number.isFinite)) return undefined;
  const [x, y, scale] = parts as [number, number, number];
  return scale > 0 ? { x, y, scale } : undefined;
}

function readShown(value: string | null): Shown | undefined {
  if (value === null) return undefined;
  const on = new Set(value.split(','));
  return Object.fromEntries(CLASS_SPECS.map((c) => [c.key, on.has(c.key)])) as Shown;
}

function readList(value: string | null): string[] | undefined {
  const items = value?.split(',')
    .filter((item) => item.length > 0 && item.length <= ITEM_MAX)
    .slice(0, LIST_MAX);
  return items && items.length > 0 ? items : undefined;
}

/** Reads either spelling: a `w` key is the condensed one, anything else the
 *  readable params -- which is also every link written before `w` existed. */
export function readWallHash(hash: string): WallHash {
  const q = new URLSearchParams(hash.replace(/^#/, ''));
  let get = (key: Key): string | null => q.get(key);
  const packed = q.get('w');
  if (packed !== null) {
    const decoded = decodeHashJson(packed);
    if (!decoded || typeof decoded !== 'object' || Array.isArray(decoded)) return {};
    const fields = decoded as Record<string, unknown>;
    get = (key) => {
      const value = fields[KEYS[key]];
      return typeof value === 'string' ? value : null;
    };
  }
  const read: WallHash = {
    part: clean(get('part')),
    source: clean(get('source')),
    cam: readCam(get('cam')),
    caret: clean(get('caret')),
    sort: known(sortKeys(), get('sort')),
    filter: known(filterKeys(), get('filter')),
    shown: readShown(get('shown')),
    grouping: known(GROUPING_KEYS, get('group')),
    tint: known(TINT_MODES, get('tint')),
    gradient: known(RAMP_NAMES, get('gradient')),
    desc: get('desc') === '0' ? false : get('desc') === '1' ? true : undefined,
    excluded: readList(get('excl')),
    badges: readList(get('badges')),
  };
  return Object.fromEntries(Object.entries(read).filter(([, v]) => v !== undefined));
}

/** The hash to put in the address bar, `#` included, or '' for nothing worth
 *  keeping. Empty rather than a bare '#', which leaves the character behind in
 *  the bar after the lightbox closes. */
export function wallHashString(state: WallHash, condensed = false): string {
  const fields: [Key, string][] = [];
  if (state.source) fields.push(['source', state.source]);
  if (state.part) fields.push(['part', state.part]);
  if (state.cam) {
    const { x, y, scale } = state.cam;
    fields.push(['cam', `${Math.round(x)},${Math.round(y)},${+scale.toFixed(3)}`]);
  }
  if (state.caret) fields.push(['caret', state.caret]);
  // Defaults stay out, so an untouched wall still has a bare address bar.
  if (state.sort && state.sort !== 'id') fields.push(['sort', state.sort]);
  if (state.filter && state.filter !== 'all') fields.push(['filter', state.filter]);
  const shown = state.shown;
  if (shown && classKeys().some((k) => shown[k] !== DEFAULT_SHOWN[k])) {
    fields.push(['shown', classKeys().filter((k) => shown[k]).join(',')]);
  }
  if (state.grouping && state.grouping !== 'none') fields.push(['group', state.grouping]);
  // `gradient` rides only with a tint that uses it -- the sidebar hides the
  // picker under `status`, and a hash naming a ramp nothing draws in would
  // outlive the mode it was picked for.
  if (state.tint && state.tint !== 'status') {
    fields.push(['tint', state.tint]);
    if (state.gradient && state.gradient !== 'ember') {
      fields.push(['gradient', state.gradient]);
    }
  }
  if (state.desc === false) fields.push(['desc', '0']);
  if (state.excluded?.length) fields.push(['excl', state.excluded.join(',')]);
  if (state.badges?.length) fields.push(['badges', state.badges.join(',')]);
  if (fields.length === 0) return '';
  if (condensed) {
    return `#w=${encodeHashJson(Object.fromEntries(
      fields.map(([key, value]) => [KEYS[key], value])))}`;
  }
  // Commas left bare: they are legal in a fragment, and `cam=1240,880,2.4`
  // is the point of the readable spelling.
  return `#${fields.map(([key, value]) =>
    `${key}=${encodeURIComponent(value).replace(/%2C/g, ',')}`).join('&')}`;
}

/** Which parts to put on the wall, handed over by a link from another page --
 *  the dashboard's "open on the wall". In the query, not the hash, and read
 *  once: like `?part=` it is a hand-off, dropped once the wall has taken it. */
export interface WallLink {
  source?: string;
  filter?: Filter;
  /** Only the classes the link names; the rest keep the wall's defaults. */
  shown?: Partial<Shown>;
  excluded?: string[];
  badges?: string[];
}

/** Every query parameter a `WallLink` can be spelled with, so the wall can
 *  take them back out of the address bar. */
export const WALL_LINK_PARAMS: readonly string[] =
  ['source', 'filter', 'excluded', 'badges', ...CLASS_SPECS.map((c) => c.key)];

export function wallLinkQuery(link: WallLink): URLSearchParams {
  const q = new URLSearchParams();
  if (link.source) q.set('source', link.source);
  if (link.filter && link.filter !== 'all') q.set('filter', link.filter);
  for (const { key } of CLASS_SPECS) {
    const on = link.shown?.[key];
    if (on !== undefined) q.set(key, String(on));
  }
  for (const name of link.excluded ?? []) q.append('excluded', name);
  for (const tag of link.badges ?? []) q.append('badges', tag);
  return q;
}

export function readWallLink(search: string): WallLink {
  const q = new URLSearchParams(search.replace(/^\?/, ''));
  const out: WallLink = {};
  const source = clean(q.get('source'));
  const filter = known(filterKeys(), q.get('filter'));
  if (source) out.source = source;
  if (filter) out.filter = filter;
  const shown: Partial<Shown> = {};
  for (const { key } of CLASS_SPECS) {
    const value = q.get(key);
    if (value === 'true' || value === 'false') shown[key] = value === 'true';
  }
  if (Object.keys(shown).length > 0) out.shown = shown;
  const excluded = q.getAll('excluded');
  const badges = q.getAll('badges');
  if (excluded.length > 0) out.excluded = excluded;
  if (badges.length > 0) out.badges = badges;
  return out;
}
