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

  it('selects a mark pressed while armed instead of drawing over it', () => {
    const onDraw = vi.fn();
    const onSelect = vi.fn();
    const { container } = render(
      <MarkLayer {...props} onDraw={onDraw} onSelect={onSelect} defects={[defect()]} />);
    const mark = container.querySelector('.mark')!;
    fireEvent.pointerDown(mark, { clientX: 60, clientY: 40 });
    fireEvent.pointerUp(mark, { clientX: 90, clientY: 60 });
    fireEvent.click(mark);
    expect(onDraw).not.toHaveBeenCalled();
    expect(onSelect).toHaveBeenCalledWith('d1');
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

  it('marks a defect as taking the pointer, so a press on it is not a pan', () => {
    const { container } = render(
      <MarkLayer {...props} armed={false} defects={[defect()]} />);
    expect(container.querySelector('.mark')!.hasAttribute('data-no-drag')).toBe(true);
  });

  it('takes the pointer for the whole layer only while it is armed', () => {
    const armed = render(<MarkLayer {...props} defects={[]} />);
    expect(armed.container.querySelector('.mark-layer')!
      .hasAttribute('data-no-drag')).toBe(true);

    const idle = render(<MarkLayer {...props} armed={false} defects={[]} />);
    expect(idle.container.querySelector('.mark-layer')!
      .hasAttribute('data-no-drag')).toBe(false);
  });
});
