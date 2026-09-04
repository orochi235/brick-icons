import { createRef } from 'react';
import { describe, expect, it } from 'vitest';
import { createTargetRegistry } from '@lab/defects/targets';
import { HOME } from '@lab/panes/camera';

describe('createTargetRegistry', () => {
  it('has no targets before a render reports any', () => {
    expect(createTargetRegistry().targets('t1')).toEqual([]);
  });

  it('returns what the last publish gave it', () => {
    const reg = createTargetRegistry();
    const ref = createRef<HTMLDivElement>();
    reg.publish('t1', {
      camera: HOME,
      panes: [{ id: 'naive', ref, content: { w: 900, h: 900 } }],
    });
    const t = reg.targets('t1')[0]!;
    expect(t.id).toBe('pane:naive');
    expect(t.ref).toBe(ref);
    expect(t.content).toEqual({ w: 900, h: 900 });
    expect(t.view).toBe(HOME);
    expect(t.positionDependsOn).toEqual(['angle', 'shading', 'shade_style']);
  });

  it('gives each pane its own content box', () => {
    const reg = createTargetRegistry();
    reg.publish('t1', {
      camera: HOME,
      panes: [
        { id: 'naive', ref: createRef(), content: { w: 800, h: 400 } },
        { id: 'occt', ref: createRef(), content: { w: 200, h: 900 } },
      ],
    });
    const [a, b] = [reg.targets('t1')[0]!, reg.targets('t1')[1]!];
    expect(a.content).toEqual({ w: 800, h: 400 });
    expect(b.content).toEqual({ w: 200, h: 900 });
  });

  it('reads the camera live, so a pan after publish is seen', () => {
    const reg = createTargetRegistry();
    reg.publish('t1', { camera: HOME, panes: [] });
    const moved = { zoom: 2, pan: { x: 10, y: 20 } };
    reg.publish('t1', {
      camera: moved,
      panes: [{ id: 'occt', ref: createRef(), content: { w: 900, h: 900 } }],
    });
    expect(reg.targets('t1')[0]?.view).toBe(moved);
  });

  it('drops panes that are no longer shown', () => {
    const reg = createTargetRegistry();
    reg.publish('t1', {
      camera: HOME,
      panes: [{ id: 'naive', ref: createRef(), content: { w: 900, h: 900 } }],
    });
    reg.publish('t1', { camera: HOME, panes: [] });
    expect(reg.targets('t1')).toEqual([]);
  });

  it('keeps two trials apart, so neither measures the other\'s panes', () => {
    const reg = createTargetRegistry();
    const a = createRef<HTMLDivElement>();
    const b = createRef<HTMLDivElement>();
    reg.publish('t1', { camera: HOME, panes: [{ id: 'naive', ref: a, content: { w: 100, h: 100 } }] });
    reg.publish('t2', { camera: HOME, panes: [{ id: 'naive', ref: b, content: { w: 900, h: 900 } }] });
    expect(reg.targets('t1')[0]!.ref).toBe(a);
    expect(reg.targets('t1')[0]!.content).toEqual({ w: 100, h: 100 });
    expect(reg.targets('t2')[0]!.ref).toBe(b);
  });

  it('forgets a trial that closed', () => {
    const reg = createTargetRegistry();
    reg.publish('t1', { camera: HOME, panes: [{ id: 'naive', ref: createRef(), content: { w: 1, h: 1 } }] });
    reg.forget('t1');
    expect(reg.targets('t1')).toEqual([]);
  });
});
