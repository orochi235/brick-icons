import type { RefObject } from 'react';
import type { AnnotationTarget, CaptureSource } from '@weasel-js/labkit';
import type { Camera } from '@lab/panes/camera';
import type { SourceId } from '@lab/panes/sources';

/** The config keys whose change means a stored fraction no longer points at
 *  the same picture. labkit snapshots these onto every mark and answers
 *  `isStale` from them, which is why the lab no longer computes staleness. */
export const POSITION_DEPENDS_ON = ['angle', 'shading', 'shade_style'] as const;

export interface PaneEntry {
  id: SourceId;
  ref: RefObject<HTMLElement | null>;
  content: { w: number; h: number };
  base?: () => CaptureSource;
}

export interface TargetSnapshot {
  camera: Camera;
  panes: readonly PaneEntry[];
}

export interface TargetRegistry {
  publish: (snapshot: TargetSnapshot) => void;
  targets: () => readonly AnnotationTarget[];
}

/** `annotations.targets` is handed only `(state, config)`, so it cannot reach
 *  the pane refs or the trial's camera. The instrument holds one of these and
 *  `Panes` republishes on every render. */
export function createTargetRegistry(): TargetRegistry {
  let current: TargetSnapshot | null = null;
  return {
    publish: (snapshot) => { current = snapshot; },
    targets: () => {
      if (!current) return [];
      const { camera, panes } = current;
      return panes.map((p) => ({
        id: `pane:${p.id}`,
        ref: p.ref,
        content: p.content,
        view: camera,
        positionDependsOn: POSITION_DEPENDS_ON,
        ...(p.base ? { base: p.base } : {}),
      }));
    },
  };
}
