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
  /** What the cells are colored by. Here because a wall tinted by render
   *  seconds is a different picture of the corpus, not a view setting: a
   *  link to it that arrives colored by status shows the reader something
   *  else and says nothing about it. */
  tint?: TintMode;
  /** The ramp a measured tint draws in. Only meaningful alongside one. */
  gradient?: RampName;
}

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

export function readWallHash(hash: string): WallHash {
  const q = new URLSearchParams(hash.replace(/^#/, ''));
  const out: WallHash = {};
  const part = clean(q.get('part'));
  const source = clean(q.get('source'));
  const tint = known(TINT_MODES, q.get('tint'));
  const gradient = known(RAMP_NAMES, q.get('gradient'));
  if (part) out.part = part;
  if (source) out.source = source;
  if (tint) out.tint = tint;
  if (gradient) out.gradient = gradient;
  return out;
}

/** The hash to put in the address bar, `#` included, or '' for nothing worth
 *  keeping. Empty rather than a bare '#', which leaves the character behind in
 *  the bar after the lightbox closes. */
export function wallHashString(state: WallHash): string {
  const q = new URLSearchParams();
  if (state.source) q.set('source', state.source);
  if (state.part) q.set('part', state.part);
  // Defaults stay out, so an untouched wall still has a bare address bar.
  // `gradient` rides only with a tint that uses it -- the sidebar hides the
  // picker under `status`, and a hash naming a ramp nothing draws in would
  // outlive the mode it was picked for.
  if (state.tint && state.tint !== 'status') {
    q.set('tint', state.tint);
    if (state.gradient && state.gradient !== 'ember') {
      q.set('gradient', state.gradient);
    }
  }
  const text = q.toString();
  return text ? `#${text}` : '';
}
