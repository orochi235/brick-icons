import type { SourceId } from '@lab/config/nodes';

export interface Source {
  id: SourceId;
  label: string;
  /** `engine` sources render through the CLI with `--engine` pinned. */
  kind: 'engine' | 'reference' | '3d' | 'decal' | 'diff';
}

export const SOURCES: Record<SourceId, Source> = {
  naive: { id: 'naive', label: 'naive', kind: 'engine' },
  occt: { id: 'occt', label: 'occt', kind: 'engine' },
  reference: { id: 'reference', label: 'LDView', kind: 'reference' },
  '3d': { id: '3d', label: '3D', kind: '3d' },
  decal: { id: 'decal', label: 'decal', kind: 'decal' },
  diff: { id: 'diff', label: 'diff', kind: 'diff' },
};

const ORDER: SourceId[] = ['naive', 'occt', 'reference', '3d', 'decal', 'diff'];

export function enabledSources(ids: readonly SourceId[]): Source[] {
  const wanted = new Set(ids);
  return ORDER.filter((id) => wanted.has(id)).map((id) => SOURCES[id]);
}

/** The render config for one source: an engine source pins `--engine` to
 *  itself, so two panes of one trial differ in exactly that flag. */
export function sourceConfig(source: Source, config: Record<string, unknown>) {
  if (source.kind !== 'engine') return config;
  return { ...config, engine: source.id };
}
