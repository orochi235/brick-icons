import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PartSearch } from '@lab/chrome/PartSearch';
import { takePendingPart } from '@lab/config/pending';
import type { LabClient } from '@lab/api/client';

const client = (results: { id: string; description: string; printed: boolean }[]) =>
  ({ searchParts: vi.fn(async () => results) } as unknown as LabClient);

describe('PartSearch', () => {
  it('opens a trial on the typed part when Enter is pressed', () => {
    const onOpen = vi.fn();
    render(<PartSearch client={client([])} onOpen={onOpen} />);
    const input = screen.getByPlaceholderText(/part/i);
    fireEvent.change(input, { target: { value: '3941' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onOpen).toHaveBeenCalledWith('3941');
  });

  it('leaves the part pending for the trial about to be added', () => {
    render(<PartSearch client={client([])} onOpen={() => {}} />);
    const input = screen.getByPlaceholderText(/part/i);
    fireEvent.change(input, { target: { value: '4070' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(takePendingPart()).toBe('4070');
  });

  it('does nothing on Enter with an empty field', () => {
    const onOpen = vi.fn();
    render(<PartSearch client={client([])} onOpen={onOpen} />);
    fireEvent.keyDown(screen.getByPlaceholderText(/part/i), { key: 'Enter' });
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('lists typeahead hits with their descriptions', async () => {
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText(/part/i),
      { target: { value: 'brick 2 x 4' } });
    await waitFor(() => expect(screen.getByText(/Brick 2 x 4/)).toBeTruthy());
  });

  it('opens the part a hit names when the hit is clicked', async () => {
    const onOpen = vi.fn();
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={onOpen} />);
    fireEvent.change(screen.getByPlaceholderText(/part/i), { target: { value: 'brick' } });
    await waitFor(() => screen.getByText(/Brick 2 x 4/));
    fireEvent.click(screen.getByText(/Brick 2 x 4/));
    expect(onOpen).toHaveBeenCalledWith('3001');
  });

  it('does not search on an empty query', () => {
    const api = client([]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    expect(api.searchParts).not.toHaveBeenCalled();
  });
});
