/** Sizes as a reader says them out loud.
 *
 *  Powers of 1024 with the units `du -h` prints, because that is the command
 *  anyone checking this by hand will run and a page that disagrees with it by
 *  7% invites a hunt for the missing bytes.
 */

const UNITS = ['B', 'KB', 'MB', 'GB', 'TB'] as const;

/** `bytes` at a scale that keeps three significant figures: 3.1 GB, 612 MB,
 *  0 B. Anything under a kilobyte stays in bytes. */
export function humanBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  let n = bytes;
  let unit = 0;
  while (n >= 1024 && unit < UNITS.length - 1) {
    n /= 1024;
    unit += 1;
  }
  const places = unit === 0 ? 0 : n < 10 ? 1 : 0;
  return `${n.toFixed(places)} ${UNITS[unit]}`;
}

/** `part` as a percentage of `whole`, or null when there is no whole to be a
 *  part of -- a bar with no denominator should draw nothing, not 0%. */
export function share(part: number, whole: number): number | null {
  return whole > 0 ? (part / whole) * 100 : null;
}
