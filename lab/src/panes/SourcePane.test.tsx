import { createRef } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SourcePane } from '@lab/panes/SourcePane';
import { HOME } from '@lab/panes/camera';
import { SOURCES } from '@lab/panes/sources';

const props = { camera: HOME, onCamera: () => {} };

describe('SourcePane', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth',
      { configurable: true, value: 400 });
    Object.defineProperty(HTMLElement.prototype, 'clientHeight',
      { configurable: true, value: 300 });
  });

  it('labels itself with the source', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }} />);
    expect(screen.getByText(SOURCES.naive.label)).toBeTruthy();
  });

  it('carries nothing but the label when the pane reports nothing', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.occt} state={{ kind: 'idle' }} />);
    expect(container.querySelector('.pane-note')).toBeNull();
    expect(container.textContent).toBe(SOURCES.occt.label);
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

  // Deltas come from the pointer's own coordinates rather than `movementX`,
  // which WebKit leaves at 0 for touch.
  it('pans on a drag across its body', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    fireEvent.pointerDown(body, { pointerId: 1, clientX: 30, clientY: 20 });
    fireEvent.pointerMove(body, { pointerId: 1, clientX: 40, clientY: 24 });
    expect(onCamera).toHaveBeenCalledWith({ zoom: 1, pan: { x: 10, y: 4 } });
  });

  it('leaves the drag alone when the press landed on a no-drag child', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }}
        overlay={<div data-no-drag="" className="taker" />} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    fireEvent.pointerDown(container.querySelector('.taker')!,
                          { pointerId: 1, clientX: 30, clientY: 20 });
    fireEvent.pointerMove(body, { pointerId: 1, clientX: 40, clientY: 24 });
    expect(onCamera).not.toHaveBeenCalled();
  });

  it('zooms about the fingers on a pinch, and pans no further', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    // The spread doubles about a midpoint that has moved to x=60, and the
    // first frame anchors there: the point under the fingers stays put.
    fireEvent.pointerDown(body, { pointerId: 1, clientX: 40, clientY: 0 });
    fireEvent.pointerDown(body, { pointerId: 2, clientX: 60, clientY: 0 });
    fireEvent.pointerMove(body, { pointerId: 2, clientX: 80, clientY: 0 });
    expect(onCamera).toHaveBeenCalledWith({ zoom: 2, pan: { x: -60, y: 0 } });
  });

  it('does not pan from the second finger of a pinch', () => {
    const onCamera = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} source={SOURCES.naive}
        state={{ kind: 'idle' }} />);
    const body = container.querySelector('.pane-body')!;
    body.setPointerCapture = () => {};
    fireEvent.pointerDown(body, { pointerId: 1, clientX: 40, clientY: 0 });
    fireEvent.pointerDown(body, { pointerId: 2, clientX: 60, clientY: 0 });
    fireEvent.pointerMove(body, { pointerId: 1, clientX: 10, clientY: 0 });
    // A one-finger pan would have moved 30px left at zoom 1. Every camera
    // this move produced came from the pinch, which spread the fingers.
    expect(onCamera).toHaveBeenCalled();
    for (const [cam] of onCamera.mock.calls) expect(cam.zoom).not.toBe(1);
  });

  it('draws no bubble when the loupe is not over it', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }} />);
    expect(container.querySelector('.pane-loupe')).toBeNull();
  });

  it('draws the bubble at the cursor, magnifying the same drawing', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive}
        state={{ kind: 'svg', markup: '<svg viewBox="0 0 4 4"></svg>' }}
        loupe={{ at: { x: 120, y: 80 }, factor: 4 }} />);
    const bubble = container.querySelector('.pane-loupe') as HTMLElement;
    expect(bubble.style.left).toBe('120px');
    expect(bubble.style.top).toBe('80px');
    // Two stages now: the pane's own and the magnified one.
    expect(container.querySelectorAll('.pane-stage').length).toBe(2);
    expect(container.querySelectorAll('svg').length).toBe(2);
  });

  it('magnifies by the factor off the shared camera', () => {
    const { container } = render(
      <SourcePane {...props} camera={{ zoom: 2, pan: { x: 0, y: 0 } }}
        source={SOURCES.naive} state={{ kind: 'idle' }}
        loupe={{ at: { x: 0, y: 0 }, factor: 4 }} />);
    const stages = container.querySelectorAll('.pane-stage');
    expect((stages[1] as HTMLElement).style.transform)
      .toBe('translate(0px, 0px) scale(8)');
  });

  it('shows a supplied image instead of the stage, for a pane it cannot clone', () => {
    const { container } = render(
      <SourcePane {...props} source={SOURCES['3d']} state={{ kind: 'idle' }}
        loupe={{ at: { x: 10, y: 10 }, factor: 4, image: 'data:image/png;base64,AA' }} />);
    const img = container.querySelector('.pane-loupe img') as HTMLImageElement;
    expect(img.getAttribute('src')).toBe('data:image/png;base64,AA');
  });

  it('does not re-apply the camera to a drawing that already has it', () => {
    const { container } = render(
      <SourcePane {...props} camera={{ zoom: 2, pan: { x: 100, y: 0 } }}
        source={SOURCES['3d']} state={{ kind: 'idle' }}
        loupe={{ at: { x: 0, y: 0 }, factor: 4, image: 'data:image/png;base64,AA' }} />);
    const stages = container.querySelectorAll('.pane-stage');
    // scale(4), not scale(8): the 3D snapshot is rendered at the shared camera
    // already, so the bubble magnifies it and nothing more.
    expect((stages[1] as HTMLElement).style.transform)
      .toBe('translate(0px, 0px) scale(4)');
  });

  it('reports where the pointer is, so a sibling pane can mirror it', () => {
    const onHover = vi.fn();
    const { container } = render(
      <SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
        onHover={onHover} />);
    const body = container.querySelector('.pane-body')!;
    fireEvent.pointerMove(body, { clientX: 30, clientY: 20 });
    expect(onHover).toHaveBeenCalledWith({ x: 30, y: 20 });
    fireEvent.pointerLeave(body);
    expect(onHover).toHaveBeenLastCalledWith(null);
  });

  it('zooms the shared camera on a plain wheel', () => {
    const onCamera = vi.fn();
    const onFactor = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} onFactor={onFactor}
        source={SOURCES.naive} state={{ kind: 'idle' }} />);
    fireEvent.wheel(container.querySelector('.pane-body')!, { deltaY: -1 });
    expect(onCamera).toHaveBeenCalled();
    expect(onFactor).not.toHaveBeenCalled();
  });

  it('sets the loupe factor on an Alt wheel, leaving the camera alone', () => {
    const onCamera = vi.fn();
    const onFactor = vi.fn();
    const { container } = render(
      <SourcePane {...props} onCamera={onCamera} onFactor={onFactor}
        source={SOURCES.naive} state={{ kind: 'idle' }} />);
    const body = container.querySelector('.pane-body')!;
    fireEvent.wheel(body, { deltaY: -1, altKey: true });
    expect(onFactor).toHaveBeenCalledWith(1);
    fireEvent.wheel(body, { deltaY: 1, altKey: true });
    expect(onFactor).toHaveBeenLastCalledWith(-1);
    expect(onCamera).not.toHaveBeenCalled();
  });

  it('hands the pane body to a caller-supplied ref', () => {
    const bodyRef = createRef<HTMLDivElement>();
    render(
      <SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }}
        bodyRef={bodyRef} />,
    );
    expect(bodyRef.current).not.toBeNull();
    expect(bodyRef.current?.classList.contains('pane-body')).toBe(true);
  });
});
