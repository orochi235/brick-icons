import { useCallback, useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { Mark } from '@lab/defects/geometry';
import { defectId, seenFrom, type Seen } from '@lab/defects/identity';

export type DefectStatus = 'open' | 'fixed' | 'wontfix' | 'notabug';

export interface Defect {
  id: string;
  part: string;
  engines: string[];
  status: DefectStatus;
  title: string;
  mark: Mark;
  seen: Seen;
  filed: string;
  notes: string;
}

export interface BuildDefectArgs {
  part: string;
  engines: string[];
  title: string;
  notes: string;
  mark: Mark;
  config: Record<string, unknown>;
  existing: readonly string[];
  today: string;
}

export function buildDefect(args: BuildDefectArgs): Defect {
  const title = args.title.trim();
  if (!title) throw new Error('a defect needs a title');
  return {
    id: defectId(args.part, args.engines, title, args.existing),
    part: args.part,
    engines: [...args.engines].sort(),
    status: 'open',
    title,
    mark: args.mark,
    seen: seenFrom(args.config),
    filed: args.today,
    notes: args.notes,
  };
}

/** Every mounted hook, by the part it is watching.
 *
 * The panes and the status bar each hold their own `useDefects`, and a write
 * through one leaves the others showing the store as it was -- a count that
 * reads `no defects` beside a mark that is plainly drawn. A write notifies
 * every hook on the same part, and no hook on another. */
const watchers = new Map<string, Set<() => void>>();

function notify(part: string) {
  for (const listener of watchers.get(part) ?? []) listener();
}

/** A part's defects, and the two ways they change. */
export function useDefects(client: LabClient, part: string) {
  const [defects, setDefects] = useState<Defect[]>([]);

  const reload = useCallback(async () => {
    if (!part.trim()) {
      setDefects([]);
      return;
    }
    setDefects((await client.defects(part)) as Defect[]);
  }, [client, part]);

  useEffect(() => {
    void reload();
    const key = part.trim();
    if (!key) return;
    const listener = () => { void reload(); };
    const set = watchers.get(key) ?? new Set();
    set.add(listener);
    watchers.set(key, set);
    return () => {
      set.delete(listener);
      if (set.size === 0) watchers.delete(key);
    };
  }, [reload, part]);

  const file = useCallback(async (record: Defect) => {
    await client.addDefect(record);
    await reload();
    notify(part.trim());
  }, [client, reload, part]);

  const setStatus = useCallback(async (id: string, status: DefectStatus) => {
    await client.patchDefect(id, { status });
    await reload();
    notify(part.trim());
  }, [client, reload, part]);

  return { defects, file, setStatus, reload };
}
