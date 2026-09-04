import { createRef } from 'react';
import { describe, expect, it } from 'vitest';
import { createTargetRegistry } from '@lab/defects/targets';
import { HOME } from '@lab/panes/camera';

describe('createTargetRegistry', () => {
  it('has no targets before a render reports any', () => {
    expect(createTargetRegistry().targets()).toEqual([]);
  });

  it('returns what the last publish gave it', () => {
    const reg = createTargetRegistry();
    const ref = createRef<HTMLDivElement>();
    reg.publish({
      camera: HOME,
      panes: [{ id: 'naive', ref, content: { w: 900, h: 900 } }],
    });
    const t = reg.targets()[0]!;
    expect(t.id).toBe('pane:naive');
    expect(t.ref).toBe(ref);
    expect(t.content).toEqual({ w: 900, h: 900 });
    expect(t.view).toBe(HOME);
    expect(t.positionDependsOn).toEqual(['angle', 'shading', 'shade_style']);
  });

  it('gives each pane its own content box', () => {
    const reg = createTargetRegistry();
    reg.publish({
      camera: HOME,
      panes: [
        { id: 'naive', ref: createRef(), content: { w: 800, h: 400 } },
        { id: 'occt', ref: createRef(), content: { w: 200, h: 900 } },
      ],
    });
    const [a, b] = [reg.targets()[0]!, reg.targets()[1]!];
    expect(a.content).toEqual({ w: 800, h: 400 });
    expect(b.content).toEqual({ w: 200, h: 900 });
  });

  it('reads the camera live, so a pan after publish is seen', () => {
    const reg = createTargetRegistry();
    reg.publish({ camera: HOME, panes: [] });
    const moved = { zoom: 2, pan: { x: 10, y: 20 } };
    reg.publish({
      camera: moved,
      panes: [{ id: 'occt', ref: createRef(), content: { w: 900, h: 900 } }],
    });
    expect(reg.targets()[0]?.view).toBe(moved);
  });

  it('drops panes that are no longer shown', () => {
    const reg = createTargetRegistry();
    reg.publish({
      camera: HOME,
      panes: [{ id: 'naive', ref: createRef(), content: { w: 900, h: 900 } }],
    });
    reg.publish({ camera: HOME, panes: [] });
    expect(reg.targets()).toEqual([]);
  });
});
