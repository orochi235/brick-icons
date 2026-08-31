import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DefectList, sortDefects } from '@lab/defects/DefectList';
import type { Defect } from '@lab/defects/useDefects';

const d = (over: Partial<Defect>): Defect => ({
  id: 'd1', part: '3941', engines: ['occt'], status: 'open', title: 'a',
  mark: { x: 0, y: 0, w: 1, h: 1 }, seen: {}, filed: '2026-08-31', notes: '',
  ...over,
});

describe('sortDefects', () => {
  it('puts open before fixed', () => {
    const got = sortDefects([d({ id: 'a', status: 'fixed' }), d({ id: 'b' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });

  it('orders by part within a status', () => {
    const got = sortDefects([d({ id: 'a', part: '4070' }), d({ id: 'b', part: '3941' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });

  it('puts notabug last, since it is not work', () => {
    const got = sortDefects([d({ id: 'a', status: 'notabug' }),
                             d({ id: 'b', status: 'wontfix' })]);
    expect(got.map((x) => x.id)).toEqual(['b', 'a']);
  });
});

describe('DefectList', () => {
  const props = { onOpen: () => {}, onStatus: () => {} };

  it('lists every defect', () => {
    render(<DefectList {...props} defects={[d({ id: 'a', title: 'one' }),
                                            d({ id: 'b', title: 'two' })]} />);
    expect(screen.getByText('one')).toBeTruthy();
    expect(screen.getByText('two')).toBeTruthy();
  });

  it('says so when there are none', () => {
    render(<DefectList {...props} defects={[]} />);
    expect(screen.getByText(/no defects/i)).toBeTruthy();
  });

  it('filters by status', () => {
    render(<DefectList {...props} defects={[d({ id: 'a', title: 'one' }),
      d({ id: 'b', title: 'two', status: 'fixed' })]} />);
    fireEvent.change(screen.getByLabelText(/status/i), { target: { value: 'fixed' } });
    expect(screen.queryByText('one')).toBeNull();
    expect(screen.getByText('two')).toBeTruthy();
  });

  it('opens the part when a row is activated', () => {
    const onOpen = vi.fn();
    render(<DefectList {...props} onOpen={onOpen} defects={[d({ part: '4070' })]} />);
    fireEvent.click(screen.getByText('a'));
    expect(onOpen).toHaveBeenCalledWith('4070', 'd1');
  });

  it('changes a status', () => {
    const onStatus = vi.fn();
    render(<DefectList {...props} onStatus={onStatus} defects={[d({})]} />);
    fireEvent.change(screen.getAllByLabelText(/state of/i)[0]!,
      { target: { value: 'fixed' } });
    expect(onStatus).toHaveBeenCalledWith('d1', 'fixed');
  });
});
