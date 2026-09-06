import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { DEFAULT_PARAMS } from '@lab/corpus/params';
import { ParamsPanel } from '@lab/corpus/ParamsPanel';

it('renders a heading per group', () => {
  render(<ParamsPanel params={DEFAULT_PARAMS} setParam={vi.fn()} reset={vi.fn()} />);
  expect(screen.getByText('Layout')).toBeTruthy();
  expect(screen.getByText('Appearance')).toBeTruthy();
  expect(screen.getByText('Feel')).toBeTruthy();
});

it('writes a slider change through setParam', () => {
  const setParam = vi.fn();
  const { container } = render(
    <ParamsPanel params={DEFAULT_PARAMS} setParam={setParam} reset={vi.fn()} />,
  );
  // Layout's first field, `cell`, is the first range input in the panel.
  const slider = container.querySelector('input[type="range"]')!;
  fireEvent.change(slider, { target: { value: '64' } });
  expect(setParam).toHaveBeenCalledWith('cell', 64);
});

it('writes a color change through setParam', () => {
  const setParam = vi.fn();
  const { container } = render(
    <ParamsPanel params={DEFAULT_PARAMS} setParam={setParam} reset={vi.fn()} />,
  );
  const swatch = container.querySelector('input[type="color"]')!;
  fireEvent.change(swatch, { target: { value: '#123456' } });
  expect(setParam).toHaveBeenCalledWith(expect.any(String), '#123456');
});

it('calls reset from its own button', () => {
  const reset = vi.fn();
  render(<ParamsPanel params={DEFAULT_PARAMS} setParam={vi.fn()} reset={reset} />);
  fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
  expect(reset).toHaveBeenCalled();
});

it('closes on its own dismissal', () => {
  const { container } = render(
    <ParamsPanel params={DEFAULT_PARAMS} setParam={vi.fn()} reset={vi.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: /close params/i }));
  expect(container.querySelector('.corpus-params-panel')).toBeNull();
});
