import { describe, expect, it } from 'vitest';
import { markToScreen } from '@lab/defects/geometry';
import { fracToWorld } from '@weasel-js/labkit';
import { HOME } from '@lab/panes/camera';

describe('a stored fraction means the same thing on both sides', () => {
  const mark = { x: 0.25, y: 0.5, w: 0.1, h: 0.2 };

  it('agrees when the pane body is square, as the render is', () => {
    const box = { width: 900, height: 900 };
    const screen = markToScreen(mark, box, HOME);
    const world = fracToWorld(mark, { w: 900, h: 900 });
    expect(world.x).toBeCloseTo(screen.left);
    expect(world.y).toBeCloseTo(screen.top);
    expect(world.width).toBeCloseTo(screen.width);
  });

  it('DISAGREES when the pane body is not square — this is the hazard', () => {
    const box = { width: 1200, height: 600 };
    const screen = markToScreen(mark, box, HOME);
    const world = fracToWorld(mark, { w: 900, h: 900 });
    expect(world.x).not.toBeCloseTo(screen.left);
  });
});
