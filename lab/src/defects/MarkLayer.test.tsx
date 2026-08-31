import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkLayer } from '@lab/defects/MarkLayer';
import { HOME } from '@lab/panes/camera';
import type { Defect } from '@lab/defects/useDefects';

const defect = (over: Partial<Defect> = {}): Defect => ({
  id: 'd1', part: '3941', engines: ['occt'], status: 'open',
  title: 'borehole rim not drawn', mark: { x: 0.25, y: 0.25, w: 0.5, h: 0.5 },
  seen: { angle: '30,25' }, filed: '2026-08-31', notes: '', ...over,
});

const props = {
  box: { width: 200, height: 100 },
  camera: HOME,
  config: { angle: '30,25' },
  armed: true,
  onDraw: () => {},
  onSelect: () => {},
};

describe('MarkLayer', () => {
  it('draws one box per defect', () => {
    const { container } = render(
      <MarkLayer {...props} defects={[defect(), defect({ id: 'd2' })]} />);
    expect(container.querySelectorAll('.mark')).toHaveLength(2);
  });

  it('places a mark where the geometry says', () => {
    const { container } = render(<MarkLayer {...props} defects={[defect()]} />);
    const box = container.querySelector('.mark') as HTMLElement;
    expect(box.style.left).toBe('50px');
    expect(box.style.width).toBe('100px');
  });

  it('marks a stale defect so it is not read as a hit', () => {
    const { container } = render(
      <MarkLayer {...props} config={{ angle: '45,45' }} defects={[defect()]} />);
    expect(container.querySelector('.mark-stale')).toBeTruthy();
  });

  it('labels a mark with its defect title', () => {
    render(<MarkLayer {...props} defects={[defect()]} />);
    expect(screen.getByTitle(/borehole rim not drawn/)).toBeTruthy();
  });

  it('selects a defect when its mark is clicked', () => {
    const onSelect = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onSelect={onSelect} defects={[defect()]} />);
    fireEvent.click(container.querySelector('.mark')!);
    expect(onSelect).toHaveBeenCalledWith('d1');
  });

  it('reports a completed drag as a mark', () => {
    const onDraw = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onDraw={onDraw} defects={[]} />);
    const surface = container.querySelector('.mark-layer')!;
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 10 });
    fireEvent.pointerMove(surface, { clientX: 60, clientY: 30 });
    fireEvent.pointerUp(surface, { clientX: 60, clientY: 30 });
    expect(onDraw).toHaveBeenCalledWith({ x: 0.1, y: 0.1, w: 0.2, h: 0.2 });
  });

  it('ignores a click that drew nothing', () => {
    const onDraw = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onDraw={onDraw} defects={[]} />);
    const surface = container.querySelector('.mark-layer')!;
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 10 });
    fireEvent.pointerUp(surface, { clientX: 20, clientY: 10 });
    expect(onDraw).not.toHaveBeenCalled();
  });

  // The layer covers the whole pane body, which owns the pan. Unarmed it must
  // let a drag through to that; armed it must not pan while drawing.
  it('draws nothing when it is not armed', () => {
    const onDraw = vi.fn();
    const { container } = render(
      <MarkLayer {...props} armed={false} onDraw={onDraw} defects={[]} />);
    const surface = container.querySelector('.mark-layer')!;
    fireEvent.pointerDown(surface, { clientX: 20, clientY: 10 });
    fireEvent.pointerUp(surface, { clientX: 60, clientY: 30 });
    expect(onDraw).not.toHaveBeenCalled();
  });

  it('is inert to the pointer when it is not armed', () => {
    const { container } = render(
      <MarkLayer {...props} armed={false} defects={[defect()]} />);
    expect(container.querySelector('.mark-layer-armed')).toBeNull();
  });

  it('keeps a press on a mark off the pane beneath it', () => {
    const onPointerDown = vi.fn();
    const { container } = render(
      <div onPointerDown={onPointerDown}>
        <MarkLayer {...props} armed={false} defects={[defect()]} />
      </div>);
    fireEvent.pointerDown(container.querySelector('.mark')!, { clientX: 60, clientY: 40 });
    expect(onPointerDown).not.toHaveBeenCalled();
  });

  it('keeps a drag off the pane beneath it', () => {
    const onPointerDown = vi.fn();
    const { container } = render(
      <div onPointerDown={onPointerDown}>
        <MarkLayer {...props} defects={[]} />
      </div>);
    fireEvent.pointerDown(container.querySelector('.mark-layer')!,
      { clientX: 20, clientY: 10 });
    expect(onPointerDown).not.toHaveBeenCalled();
  });
});
