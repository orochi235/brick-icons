import type { ReactNode } from 'react';
import type { PaneState } from '@lab/panes/SourcePane';
import type { Source, SourceId } from '@lab/panes/sources';
import { enginePaneState, type EngineRenders } from '@lab/panes/engineState';

/** Everything one pane needs that the others do not supply themselves. The
 *  caller runs the hooks and passes what they produced, so this stays a pure
 *  function of a source and the run around it. */
export interface PaneDeps {
  engines: EngineRenders;
  markup: Partial<Record<SourceId, string>>;
  run: { signature: string; running: boolean };
  reference: PaneState;
  decal: { pane: PaneState; note?: string };
  diff: { pane: PaneState; note?: string };
  /** The 3D pane's orbit view, built by the caller because it is JSX, and
   *  what it has to say about how far it is registered with the rest. */
  three: { node: ReactNode; note?: string };
}

export interface PaneSpec {
  state: PaneState;
  busy: boolean;
  note?: string;
  /** Drawn above the stage and owned by the kind, unlike the mark layer the
   *  caller adds. */
  overlay?: ReactNode;
  /** A mark is a fraction of the render it was drawn on, so it belongs only
   *  on a pane showing that render at the shared camera. */
  marks: boolean;
  /** Whether the shared camera reads and writes this pane. */
  followsCamera: boolean;
}

export function paneSpec(source: Source, deps: PaneDeps): PaneSpec {
  switch (source.kind) {
    case 'engine': {
      const engine = enginePaneState(source.id, deps.engines, deps.markup, deps.run);
      return { state: engine.pane, busy: engine.busy, marks: true, followsCamera: true };
    }
    case 'diff':
      // A defect names engines, and `diff` is not one, so a mark drawn here
      // could never be found again. It comes back when a defect can name a
      // pane rather than an engine.
      return { state: deps.diff.pane, busy: false, note: deps.diff.note,
               marks: false, followsCamera: true };
    case 'reference':
      return { state: deps.reference, busy: false, marks: false, followsCamera: true };
    case 'decal':
      return { state: deps.decal.pane, busy: false, note: deps.decal.note,
               marks: false, followsCamera: true };
    case '3d':
      return { state: { kind: 'idle' }, busy: false, overlay: deps.three.node,
               note: deps.three.note, marks: false, followsCamera: true };
  }
}
