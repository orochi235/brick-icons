import { expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Fingerprint } from '@lab/corpus/Fingerprint';

const features = {
  cylinder: null, elliptical: null, off_axis: null,
  tris: 82, quads: 216, 'skew-deg': 14.5,
};

it('draws the flags a part carries and none it does not', () => {
  render(<Fingerprint features={features} />);
  expect(screen.getByText('elliptical')).toBeTruthy();
  expect(screen.queryByText('torus')).toBeNull();
});

it('tells a flag from a measure by the null, not by a list of its own', () => {
  render(<Fingerprint features={{ 'made-up-flag': null, 'made-up-count': 3 }} />);
  expect(document.querySelectorAll('.corpus-built-flag').length).toBe(1);
  expect(document.querySelectorAll('.corpus-built-measure').length).toBe(1);
});

it('keeps a measure at zero, which a flag test on falsiness would drop', () => {
  render(<Fingerprint features={{ tris: 0 }} />);
  expect(screen.getByText('0')).toBeTruthy();
  expect(document.querySelectorAll('.corpus-built-flag').length).toBe(0);
});

it('gives degrees their decimals and counts none', () => {
  render(<Fingerprint features={features} />);
  expect(screen.getByText('14.50')).toBeTruthy();
  expect(screen.getByText('82')).toBeTruthy();
});

it('draws nothing at all for an API that sends no features', () => {
  const { container } = render(<Fingerprint />);
  expect(container.querySelector('.corpus-built')).toBeNull();
});
