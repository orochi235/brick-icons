import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { SourcePane } from '@lab/panes/SourcePane';
import { HOME } from '@lab/panes/camera';
import { SOURCES } from '@lab/panes/sources';

const props = { camera: HOME, onCamera: () => {} };

describe('SourcePane', () => {
  it('labels itself with the source', () => {
    render(<SourcePane {...props} source={SOURCES.naive} state={{ kind: 'idle' }} />);
    expect(screen.getByText('naive')).toBeTruthy();
  });

  it('shows the caveat when the source has one', () => {
    render(<SourcePane {...props} source={SOURCES.occt} state={{ kind: 'idle' }} />);
    expect(screen.getByText(/strokes only/)).toBeTruthy();
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
});
