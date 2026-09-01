export type SourceKind = 'engine' | 'reference' | '3d' | 'decal' | 'diff';

/** Every pane the lab can show, in the order they are laid out. The pane's
 *  id, its `SourceId` type, the toggle bar and the render fan-out all derive
 *  from this list, so a new pane is one entry here and nothing else. */
const CATALOG = [
  { id: 'naive', label: 'naive', kind: 'engine' },
  { id: 'occt', label: 'occt', kind: 'engine' },
  { id: 'cadquery', label: 'cadquery', kind: 'engine' },
  { id: 'reference', label: 'LDView', kind: 'reference' },
  { id: '3d', label: '3D', kind: '3d' },
  { id: 'decal', label: 'decal', kind: 'decal' },
  { id: 'diff', label: 'diff', kind: 'diff' },
] as const satisfies readonly { id: string; label: string; kind: SourceKind }[];

export type SourceId = (typeof CATALOG)[number]['id'];

export interface Source {
  id: SourceId;
  label: string;
  /** `engine` sources render through the CLI with `--engine` pinned. */
  kind: SourceKind;
}

export const SOURCE_ORDER: readonly Source[] = CATALOG;

export const SOURCES = Object.fromEntries(
  CATALOG.map((source) => [source.id, source as Source]),
) as Record<SourceId, Source>;

/** Which panes a new trial opens with. */
export const DEFAULT_SOURCES: readonly SourceId[] = ['naive', 'occt'];

export function enabledSources(ids: readonly SourceId[]): Source[] {
  const wanted = new Set<string>(ids);
  return SOURCE_ORDER.filter((source) => wanted.has(source.id));
}

/** The render config for one source: an engine source pins `--engine` to
 *  itself, so two panes of one trial differ in exactly that flag. */
export function sourceConfig(source: Source, config: Record<string, unknown>) {
  if (source.kind !== 'engine') return config;
  return { ...config, engine: source.id };
}
