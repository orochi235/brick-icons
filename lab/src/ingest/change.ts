/** Whether a run's row moved the part, and which way.
 *
 *  A run's list is mostly parts that did what they did last time, and the
 *  reason to read it is the handful that did not: a slot that started drawing
 *  a part, or stopped. The rows already carry `prior`, so this is a
 *  comparison rather than anything the server has to record.
 */

/** How good an outcome is, as one of three ranks rather than a boolean: a
 *  part the engine drew nothing for did not fail -- the decal finder reports
 *  `none` for 2,913 parts it found no decoration on -- but it is not a
 *  drawing either, so `none` -> `stored` is a gain and the reverse is a loss.
 *
 *  Anything unrecognized ranks with the failures. The vocabulary that matters
 *  is the error names, and they are open-ended: a new one has to read as bad
 *  rather than as unchanged. */
const RANK: Record<string, number> = { stored: 2, drawn: 2, none: 1, '': 1 };

function rank(outcome: string): number {
  return RANK[outcome] ?? 0;
}

/** The two tables say the same thing in different words: a store run records
 *  `stored` and a census records a drawing, which `prior` and `outcomeOf`
 *  both call `drawn`. Compared raw, a part stored by one run and measured by
 *  the next reads as having changed when nothing happened to it. */
const SAME: Record<string, string> = { stored: 'drawn', '': 'none' };

function canon(outcome: string): string {
  return SAME[outcome] ?? outcome;
}

export type Change = 'first' | 'fixed' | 'broke' | 'changed' | null;

/** What a row says happened, as `prior` and the current outcome are both
 *  written: an error name, or a state.
 *
 *  A measurement carries no state and an error only when it failed, so a
 *  clean one reads `drawn` -- the same word `prior` uses for a drawing that
 *  is already in the slot. */
export function outcomeOf(row: { state: string | null; error: string | null }): string {
  return row.error ?? row.state ?? 'drawn';
}

export function changeOf(prior: string | null, now: string): Change {
  if (prior === null) return 'first';
  if (canon(prior) === canon(now)) return null;
  const from = rank(prior);
  const to = rank(now);
  if (to > from) return 'fixed';
  if (to < from) return 'broke';
  return 'changed';
}
