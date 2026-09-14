import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PartSearch } from '@lab/shared/PartSearch';
import type { LabClient } from '@lab/api/client';

// The kit's combo box opens its list only while the input has focus, as it
// does for someone typing, so a bare change event never shows the options.
const typeInto = (value: string) => {
  const input = screen.getByPlaceholderText(/part/i);
  act(() => input.focus());
  fireEvent.change(input, { target: { value } });
  return input;
};

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

  it('does nothing on Enter with an empty field', () => {
    const onOpen = vi.fn();
    render(<PartSearch client={client([])} onOpen={onOpen} />);
    fireEvent.keyDown(screen.getByPlaceholderText(/part/i), { key: 'Enter' });
    expect(onOpen).not.toHaveBeenCalled();
  });

  it('lists typeahead hits with their descriptions', async () => {
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    typeInto('brick 2 x 4');
    await waitFor(() => expect(screen.getByText(/Brick 2 x 4/)).toBeTruthy());
  });

  it('opens the part a hit names when the hit is clicked', async () => {
    const onOpen = vi.fn();
    const api = client([{ id: '3001', description: 'Brick  2 x  4', printed: false }]);
    render(<PartSearch client={api} onOpen={onOpen} />);
    typeInto('brick');
    await waitFor(() => screen.getByText(/Brick 2 x 4/));
    fireEvent.click(screen.getByText(/Brick 2 x 4/));
    expect(onOpen).toHaveBeenCalledWith('3001');
  });

  it('does not search on an empty query', () => {
    const api = client([]);
    render(<PartSearch client={api} onOpen={() => {}} />);
    expect(api.searchParts).not.toHaveBeenCalled();
  });

  it('says the search failed rather than that nothing matched', async () => {
    const api = { searchParts: vi.fn(async () => { throw new Error('502'); }) } as unknown as LabClient;
    render(<PartSearch client={api} onOpen={() => {}} />);
    typeInto('brick');
    await waitFor(() => expect(screen.getByText('search failed')).toBeTruthy());
    expect(screen.queryByText('no parts match')).toBeNull();
  });

  it('gives up on a search a later keystroke overtakes', async () => {
    const signals: AbortSignal[] = [];
    const api = {
      searchParts: vi.fn((_q: string, _limit: number, signal: AbortSignal) => {
        signals.push(signal);
        return new Promise(() => {});
      }),
    } as unknown as LabClient;
    render(<PartSearch client={api} onOpen={() => {}} />);
    const input = screen.getByPlaceholderText(/part/i);
    fireEvent.change(input, { target: { value: 'bri' } });
    await waitFor(() => expect(signals).toHaveLength(1));
    fireEvent.change(input, { target: { value: 'brick' } });
    await waitFor(() => expect(signals).toHaveLength(2));
    expect(signals[0]!.aborted).toBe(true);
  });
});
