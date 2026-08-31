/** The part a trial about to be added should open on.
 *
 * labkit's `addTrial(name)` takes no initial config, and calls the
 * instrument's `defaultConfig()` synchronously -- so a value set immediately
 * before the call is read by that trial and no other. Consumed on read, so a
 * trial added any other way opens empty.
 *
 * Remove this once labkit accepts `addTrial(name, { config })`.
 */
let pending = '';

export function setPendingPart(part: string): void {
  pending = part.trim();
}

export function takePendingPart(): string {
  const part = pending;
  pending = '';
  return part;
}
