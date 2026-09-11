import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TintScale } from '@lab/corpus/TintScale';
import { MEASURED_MODES, STEPS } from '@lab/corpus/tint';

describe('TintScale', () => {
  it('names what the colors mean and the range they span', () => {
    render(<TintScale mode="secs" gradient="ember" />);
    expect(screen.getByText('render seconds')).toBeTruthy();
    expect(screen.getByText('1.0s')).toBeTruthy();
    expect(screen.getByText('680s')).toBeTruthy();
  });

  it('says when the ramp is logarithmic, and does not when it is not', () => {
    const { unmount } = render(<TintScale mode="secs" gradient="ember" />);
    expect(screen.queryByText('log')).toBeTruthy();
    unmount();
    render(<TintScale mode="year" gradient="ember" />);
    expect(screen.queryByText('log')).toBeNull();
  });

  it('draws one swatch per quantised step, not a smooth gradient', () => {
    const { container } = render(<TintScale mode="secs" gradient="ember" />);
    const strip = container.querySelector('.corpus-tint-scale-strip')!;
    expect(strip.querySelectorAll('.corpus-tint-scale-swatch')).toHaveLength(STEPS);
  });

  it('is read-only: nothing to click, nothing to focus', () => {
    const { container } = render(<TintScale mode="sets" gradient="viridis" />);
    expect(container.querySelectorAll('button, a, input, [tabindex]')).toHaveLength(0);
    expect(container.querySelectorAll('[onclick]')).toHaveLength(0);
  });

  it('gives the strip a role and a name rather than bare swatches', () => {
    render(<TintScale mode="secs" gradient="ember" />);
    const strip = screen.getByRole('img');
    expect(strip.getAttribute('aria-label')).toContain('render seconds');
    expect(strip.getAttribute('aria-label')).toContain('logarithmic');
  });

  it('renders every measured mode', () => {
    for (const mode of MEASURED_MODES) {
      const { unmount, container } = render(
        <TintScale mode={mode} gradient="magma" />);
      expect(container.querySelector('.corpus-tint-scale')).toBeTruthy();
      unmount();
    }
  });
});
