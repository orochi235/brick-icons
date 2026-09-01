import type { SourceId } from '@lab/config/nodes';

export interface Source {
  id: SourceId;
  label: string;
  /** `engine` sources render through the CLI with `--engine` pinned. */
  kind: 'engine' | 'reference' | '3d' | 'decal' | 'diff';
  /** Shown on the pane. Names a way the pane can look wrong while being right. */
  caveat?: string;
}

export const SOURCES: Record<SourceId, Source> = {
  naive: { id: 'naive', label: 'naive', kind: 'engine' },
  occt: {
    id: 'occt', label: 'occt', kind: 'engine',
    caveat: 'strokes only — every filled mode degrades to an outline',
  },
  reference: { id: 'reference', label: 'LDView', kind: 'reference' },
  '3d': {
    id: '3d', label: '3D', kind: '3d',
    caveat: 'LDrawLoader’s own parse — not the engine’s geometry, not LDView',
  },
  decal: {
    id: 'decal', label: 'decal', kind: 'decal',
    caveat: 'the print unwrapped flat — a part with none says so',
  },
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
