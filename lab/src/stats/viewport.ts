/** What the page is SHOWING, as against which parts it counts.
 *
 *  The working set lives in the query string because it decides the numbers:
 *  a link you send has to name the same parts. This is the other half -- where
 *  you had scrolled to, which bands you had clicked off -- and it lives in the
 *  hash, so a reload puts you back where you were without ever changing what
 *  a link reports. The page takes seconds to answer over 20,000 parts, and
 *  landing back at the top of it after every reload is the cost of not
 *  keeping this.
 */
export interface Viewport {
  /** Pixels scrolled from the top of the document. */
  y: number;
  /** Coverage labels clicked off in the legend. */
  hide: string[];
  /** Phase segments clicked off. */
  hidePhase: string[];
}

export const DEFAULT_VIEWPORT: Viewport = { y: 0, hide: [], hidePhase: [] };

/** A hash for a viewport, empty where there is nothing worth carrying. The
 *  leading `#` is not included: the caller owns the rest of the address. */
export function toHash(view: Viewport): string {
  const q = new URLSearchParams();
  if (view.y > 0) q.set('y', String(Math.round(view.y)));
  if (view.hide.length) q.set('hide', view.hide.join(','));
  if (view.hidePhase.length) q.set('phase', view.hidePhase.join(','));
  return q.toString();
}

const list = (raw: string | null): string[] =>
  (raw ? raw.split(',').filter(Boolean) : []);

export function fromHash(hash: string): Viewport {
  const q = new URLSearchParams(hash.replace(/^#/, ''));
  // A hash someone typed, or one from an older bundle, must not throw the
  // page away: anything unreadable reads as the default rather than NaN.
  const y = Number(q.get('y'));
  return {
    y: Number.isFinite(y) && y > 0 ? y : 0,
    hide: list(q.get('hide')),
    hidePhase: list(q.get('phase')),
  };
}
