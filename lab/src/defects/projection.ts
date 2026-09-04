import type { AnnotationInit, AnnotationsApi } from '@weasel-js/labkit';
import type { Defect, Mark, MarkKind } from '@lab/defects/useDefects';
import type { SourceId } from '@lab/panes/sources';

/** What the lab writes into a mark's `meta`, and reads back to trace a mark
 *  to the record the server owns. */
export interface MarkMeta {
  defectId: string;
}

export const targetId = (source: string) => `pane:${source}`;
export const sourceOfTarget = (target: string) => target.replace(/^pane:/, '') as SourceId;

/** One mark per engine the defect names that currently has a pane. The server
 *  owns the record; these are its projection, remade on every reload. */
export function defectToMarks(
  defect: Defect,
  shown: readonly string[],
): AnnotationInit[] {
  return defect.engines
    .map(targetId)
    .filter((t) => shown.includes(t))
    .map((target) => ({
      target,
      kind: defect.kind ?? 'rect',
      frac: defect.mark,
      ...(defect.points?.length ? { points: defect.points } : {}),
      title: defect.title,
      status: defect.status,
      // Minted per mark: sharing one object would make a write through any
      // sibling's meta reach all of them.
      meta: { defectId: defect.id } satisfies MarkMeta,
    }));
}

/** The geometry half of a defect, taken off a mark the user just drew. The
 *  meaning half comes from the file dialog. */
export function markToDefectFields(mark: {
  id: string;
  target: string;
  kind: MarkKind;
  frac: Mark;
  points?: readonly { x: number; y: number }[];
}): {
  mark: Mark;
  engine: SourceId;
  kind?: MarkKind;
  points?: { x: number; y: number }[];
} {
  return {
    mark: mark.frac,
    engine: sourceOfTarget(mark.target),
    ...(mark.kind !== 'rect' ? { kind: mark.kind } : {}),
    ...(mark.points?.length ? { points: [...mark.points] } : {}),
  };
}

/** The slice of labkit's annotations API the projection touches. */
export type MarkStore = Pick<AnnotationsApi, 'query' | 'add' | 'remove'>;

/** Redraw the defect list as marks: drop the ones a previous pass made, then
 *  put one back for every defect on a pane that is shown.
 *
 *  Each mark is dated by the defect's own `seen`, never by the live config.
 *  Passing the config would re-snapshot every mark on every projection, and a
 *  mark whose pose matches by construction can never be reported stale. */
export function projectDefects(
  marks: MarkStore,
  defects: readonly Defect[],
  shown: readonly string[],
): void {
  for (const a of marks.query()) {
    if ((a.meta as MarkMeta | undefined)?.defectId) marks.remove(a.id);
  }
  for (const d of defects) {
    for (const init of defectToMarks(d, shown)) marks.add(init, d.seen);
  }
}
