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
  if (part) out.part = part;
  if (source) out.source = source;
  return out;
}

/** The hash to put in the address bar, `#` included, or '' for nothing worth
 *  keeping. Empty rather than a bare '#', which leaves the character behind in
 *  the bar after the lightbox closes. */
export function wallHashString(state: WallHash): string {
  const q = new URLSearchParams();
  if (state.source) q.set('source', state.source);
  if (state.part) q.set('part', state.part);
  const text = q.toString();
  return text ? `#${text}` : '';
}
