import type { RenderResult } from '@lab/api/client';
import type { SourceId } from '@lab/config/nodes';
import type { PaneState } from '@lab/panes/SourcePane';

/** What the instrument has collected from the render job so far. */
export interface EngineRenders {
  renders: Partial<Record<SourceId, RenderResult>>;
  errors: Partial<Record<SourceId, string>>;
  /** The run each pane's render came from; see `renderSignature`. */
  stamps: Partial<Record<SourceId, string>>;
}

export interface EnginePane {
  pane: PaneState;
  /** A render for this pane is in flight. Whatever the pane shows is the
   *  previous one, so it draws dimmed rather than being thrown away. */
  busy: boolean;
}

/** One engine pane's own state.
 *
 * A pane is waiting until its own render has landed AND its markup has been
 * fetched -- the job reports `done` before the second half, so reading the job
 * alone blanks the pane in that window.
 */
export function enginePaneState(
  source: SourceId,
  state: EngineRenders,
  svg: Partial<Record<SourceId, string>>,
  run: { signature: string; running: boolean },
): EnginePane {
  const mine = state.stamps[source] === run.signature;
  const error = mine ? state.errors[source] : undefined;
  const markup = svg[source];
  const waiting = error === undefined && (!mine || markup === undefined);
  const inFlight = waiting && (run.running || mine);

  if (error !== undefined) return { pane: { kind: 'error', message: error }, busy: false };
  if (markup !== undefined) return { pane: { kind: 'svg', markup }, busy: inFlight };
  return { pane: inFlight ? { kind: 'running' } : { kind: 'idle' }, busy: false };
}
