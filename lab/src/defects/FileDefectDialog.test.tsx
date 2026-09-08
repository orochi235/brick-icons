import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FileDefectDialog } from '@lab/defects/FileDefectDialog';

const props = {
  part: '3941',
  mark: { x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
  engines: ['naive', 'occt'],
  onCancel: () => {},
  onFile: () => {},
};

describe('FileDefectDialog', () => {
  it('names the part it is filing against', () => {
    render(<FileDefectDialog {...props} />);
    expect(screen.getByText(/3941/)).toBeTruthy();
  });

  it('offers each visible engine', () => {
    render(<FileDefectDialog {...props} />);
    expect(screen.getByLabelText('naive')).toBeTruthy();
    expect(screen.getByLabelText('occt')).toBeTruthy();
  });

  it('files with the title, notes and checked engines', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.change(screen.getByLabelText(/title/i),
      { target: { value: 'borehole rim not drawn' } });
    fireEvent.change(screen.getByLabelText(/notes/i), { target: { value: 'only at 30,25' } });
    fireEvent.click(screen.getByLabelText('naive'));   // leave only occt checked
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).toHaveBeenCalledWith({
      title: 'borehole rim not drawn', notes: 'only at 30,25', engines: ['occt'],
    });
  });

  it('will not file without a title', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).not.toHaveBeenCalled();
  });

  it('will not file with no engine selected', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} onFile={onFile} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: 'x' } });
    fireEvent.click(screen.getByLabelText('naive'));
    fireEvent.click(screen.getByLabelText('occt'));
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).not.toHaveBeenCalled();
  });

  it('will not file before a part is loaded, and says so', () => {
    const onFile = vi.fn();
    render(<FileDefectDialog {...props} part="" onFile={onFile} />);
    fireEvent.change(screen.getByLabelText(/title/i), { target: { value: 'x' } });
    fireEvent.click(screen.getByText(/^file$/i));
    expect(onFile).not.toHaveBeenCalled();
    expect(screen.getByText(/load a part/i)).toBeTruthy();
  });

  it('cancels', () => {
    const onCancel = vi.fn();
    render(<FileDefectDialog {...props} onCancel={onCancel} />);
    fireEvent.click(screen.getByText(/cancel/i));
    expect(onCancel).toHaveBeenCalled();
  });
});
