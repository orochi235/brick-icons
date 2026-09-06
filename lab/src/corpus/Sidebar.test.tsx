import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Sidebar } from '@lab/corpus/Sidebar';
import { DEFAULT_SHOWN, type Selection } from '@lab/corpus/select';

const selection: Selection = {
  sort: 'id', filter: 'all', shown: DEFAULT_SHOWN, grouping: 'none',
  tint: 'status', excluded: [], desc: true,
};

const props = {
  selection,
  counts: new Map([['Brick', 1332], ['Duplo', 589]]),
  shown: 1332, total: 1921,
};

const facets = () => within(document.querySelectorAll('.corpus-side__facets')[0] as HTMLElement);

describe('Sidebar', () => {
  it('lists every category with its count, biggest first', () => {
    render(<Sidebar {...props} onChange={vi.fn()} />);
    const boxes = facets().getAllByRole('checkbox');
    expect(boxes.map((b) => b.getAttribute('name'))).toEqual(['Brick', 'Duplo']);
  });

  it('excludes a category when its box is cleared', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /Duplo/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: ['Duplo'] }));
  });

  it('puts a category back when its box is checked again', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} selection={{ ...selection, excluded: ['Duplo'] }}
                    onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /Duplo/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: [] }));
  });

  it('clears and restores every category at once', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: 'none' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ excluded: ['Brick', 'Duplo'] }));
  });

  it('changes the grouping', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText('Group'), { target: { value: 'release' } });
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ grouping: 'release' }));
  });

  it('offers the direction toggle only where it means something', () => {
    const { rerender } = render(<Sidebar {...props} onChange={vi.fn()} />);
    expect(screen.queryByLabelText('Newest first')).toBeNull();
    rerender(<Sidebar {...props} selection={{ ...selection, grouping: 'release' }}
                      onChange={vi.fn()} />);
    expect(screen.getByLabelText('Newest first')).toBeTruthy();
  });

  it('says how much of the corpus is on the wall', () => {
    render(<Sidebar {...props} onChange={vi.fn()} />);
    expect(screen.getByText('1332 of 1921')).toBeTruthy();
  });

  it('turns the moved redirects back on from a checkbox', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'moved' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ shown: { ...DEFAULT_SHOWN, moved: true } }));
  });

  it('takes the out-of-scope parts off the wall from a checkbox', () => {
    const onChange = vi.fn();
    render(<Sidebar {...props} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'out of scope' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ shown: { ...DEFAULT_SHOWN, outOfScope: false } }));
  });
});
