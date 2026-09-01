import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SourcePane } from '@lab/panes/SourcePane';
import { HOME } from '@lab/panes/camera';
import { SOURCES } from '@lab/panes/sources';

const props = { camera: HOME, onCamera: () => {} };

describe('SourcePane', () => {
  it('labels itself with the source', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }} />);
    expect(screen.getByText('naive')).toBeTruthy();
  });

  it('carries nothing but the label when the pane reports nothing', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.occt} state={{ kind: 'idle' }} />);
    expect(container.querySelector('.pane-note')).toBeNull();
    expect(container.textContent).toBe('occt');
  });

  it('shows a note the pane measured', () => {
    render(<SourcePane {...props} source={SOURCES.diff} note="3 components"
      state={{ kind: 'idle' }} />);
    expect(screen.getByText('3 components')).toBeTruthy();
  });

  it('holds the last drawing, dimmed, while the next render runs', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive} busy
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"></svg>' }} />);
    expect(container.querySelector('svg')).toBeTruthy();
    expect(container.querySelector('.pane-waiting')).toBeTruthy();
    expect(screen.getByText(/rendering/i)).toBeTruthy();
  });

  it('renders the SVG inline rather than as an image', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive}
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"><rect/></svg>' }} />);
    expect(container.querySelector('svg')).toBeTruthy();
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders a raster source as an image', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.reference}
        state={{ kind: 'image', src: '/api/artifact/k/r.png' }} />);
    expect(container.querySelector('img')?.getAttribute('src'))
      .toBe('/api/artifact/k/r.png');
  });

  it('shows the error when a render failed', () => {
    render(<SourcePane {...props} source={SOURCES.occt}
      state={{ kind: 'error', message: 'TopologyException' }} />);
    expect(screen.getByText(/TopologyException/)).toBeTruthy();
  });

  it('applies the camera as a transform', () => {
    const { container } = render(
      <SourcePane {...props} camera={{ zoom: 2, pan: { x: 8, y: 4 } }}
        source={SOURCES.naive}
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"></svg>' }} />);
    const stage = container.querySelector('.pane-stage') as HTMLElement;
    expect(stage.style.transform).toBe('translate(8px, 4px) scale(2)');
  });

  it('says so while a render is in flight', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'running' }} />);
    expect(screen.getByText(/rendering/i)).toBeTruthy();
  });

  it('renders an overlay when one is given', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
        overlay={<div className="probe" />} />);
    expect(container.querySelector('.probe')).toBeTruthy();
  });

  it('reports its body size so an overlay can place marks', () => {
    const onBox = vi.fn();
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
      onBox={onBox} />);
    expect(onBox).toHaveBeenCalled();
  });

  it('pans on a drag across its body', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    fireEvent.pointerDown(body, { pointerId: 1 });
    fireEvent.pointerMove(body, { movementX: 10, movementY: 4 });
    expect(onCamera).toHaveBeenCalled();
  });

  it('leaves the drag alone when the press landed on a no-drag child', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }}
        overlay={<div data-no-drag="" className="taker" />} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    fireEvent.pointerDown(container.querySelector('.taker')!, { pointerId: 1 });
    fireEvent.pointerMove(body, { movementX: 10, movementY: 4 });
    expect(onCamera).not.toHaveBeenCalled();
  });
});
