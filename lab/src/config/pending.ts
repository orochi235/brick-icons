import { useLabContext, useLabStore } from '@weasel-js/labkit';
import type { TrialRecord } from '@weasel-js/labkit';

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

/** The trial a newly chosen part should take over: the first part inspector
 *  nobody has given a part to. `null` means every open trial is showing
 *  something, so the part needs a trial of its own.
 *
 *  Without this the lab's opening trial — which labkit creates empty — sits
 *  there for the rest of the session while every part opens beside it.
 */
export function trialToAdopt(trials: readonly TrialRecord[]): string | null {
  const empty = trials.find((t) => t.instrumentName === 'part-inspector'
    && !String((t.config as { part?: unknown }).part ?? '').trim());
  return empty ? empty.id : null;
}

/** Open a part, in an empty trial if there is one and a new trial if not. */
export function useOpenPart(): (part: string) => void {
  const { trials, addTrial } = useLabContext();
  const { updateTrialConfig } = useLabStore();
  return (part: string) => {
    const adopt = trialToAdopt(trials);
    if (adopt) {
      updateTrialConfig(adopt, 'part', part.trim());
      return;
    }
    setPendingPart(part);
    addTrial('part-inspector');
  };
}
