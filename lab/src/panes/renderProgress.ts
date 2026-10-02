import { useSyncExternalStore } from 'react';
import type { SourceId } from '@lab/panes/sources';

/** How far a pane's render has got, as the render reports it. */
export interface RenderProgress {
  fraction: number;
  phase: string;
}

// Beside the job's own events, not among them: labkit's runner counts any
// event it does not recognize as a finished item.
const current = new Map<SourceId, RenderProgress>();
const listeners = new Set<() => void>();

export function setRenderProgress(source: SourceId, p: RenderProgress | null): void {
  const was = current.get(source);
  if (p ? was?.fraction === p.fraction && was.phase === p.phase : !was) return;
  if (p) current.set(source, p);
  else current.delete(source);
  for (const fn of listeners) fn();
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function useRenderProgress(source: SourceId): RenderProgress | null {
  return useSyncExternalStore(subscribe, () => current.get(source) ?? null);
}
