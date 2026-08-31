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

  useEffect(() => { void reload(); }, [reload]);

  const file = useCallback(async (record: Defect) => {
    await client.addDefect(record);
    await reload();
  }, [client, reload]);

  const setStatus = useCallback(async (id: string, status: DefectStatus) => {
    await client.patchDefect(id, { status });
    await reload();
  }, [client, reload]);

  return { defects, file, setStatus, reload };
}
