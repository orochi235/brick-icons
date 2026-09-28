/** How long ago an ISO timestamp was, in one unit: `5m`, `2h`, `3d`, `5w`,
 *  `1y`. Always rounded down, so a tag never claims a drawing is newer than
 *  it is. `now` for anything under a minute or stamped in the future (a node's
 *  clock running ahead); null for a string that is not a time. */
export function age(iso: string, now: Date = new Date()): string | null {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return null;
  const mins = Math.floor((now.getTime() - at) / 60_000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  if (days < 365) return `${Math.floor(days / 7)}w`;
  return `${Math.floor(days / 365)}y`;
}
