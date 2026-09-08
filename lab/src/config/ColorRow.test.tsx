import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { LabClient } from '@lab/api/client';
import { ColorField } from '@lab/config/ColorRow';

const PALETTE = [
  { code: 0, name: 'Black', hex: '#1b2a34', alpha: 255, category: 'Solid', legoId: 26 },
  { code: 71, name: 'Light Bluish Grey', hex: '#969696', alpha: 255, category: 'Solid', legoId: 194 },
  { code: 72, name: 'Dark Bluish Grey', hex: '#646464', alpha: 255, category: 'Solid', legoId: 199 },
  // No LEGO number: an LDraw-only entry, offered only when 'all' is checked.
  { code: 256, name: 'Rubber Black', hex: '#1b2a34', alpha: 255, category: 'Rubber', legoId: null },
];

// A fresh object per test: the palette is cached per client, by identity.
const clientWith = (colors = PALETTE) =>
  ({ colors: vi.fn().mockResolvedValue(colors) }) as unknown as LabClient;

const props = (over: Partial<Parameters<typeof ColorField>[0]> = {}) => ({
  client: clientWith(),
  label: 'part_color',
  value: '',
  onChange: vi.fn(),
  ...over,
});

const field = () => screen.getByRole('combobox');

describe('ColorField', () => {
  it('offers nothing until it is focused', async () => {
    render(<ColorField {...props()} />);
    await waitFor(() => expect(field()).toBeTruthy());
    expect(screen.queryByRole('option')).toBeNull();
  });

  it('lists the palette on focus', async () => {
    render(<ColorField {...props()} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(3));
  });

  it('narrows to what has been typed', async () => {
    const p = props({ value: 'bluish' });
    render(<ColorField {...p} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(2));
    expect(screen.getAllByRole('option')[0]!.textContent).toContain('Light Bluish Grey');
  });

  it('writes the name a suggestion carries, not its code', async () => {
    const onChange = vi.fn();
    render(<ColorField {...props({ value: 'bluish', onChange })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option').length).toBe(2));
    fireEvent.pointerDown(screen.getAllByRole('option')[1]!);
    expect(onChange).toHaveBeenCalledWith('Dark Bluish Grey');
  });

  it('takes the arrow keys and Enter', async () => {
    const onChange = vi.fn();
    render(<ColorField {...props({ value: 'bluish', onChange })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option').length).toBe(2));
    fireEvent.keyDown(field(), { key: 'ArrowDown' });
    fireEvent.keyDown(field(), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('Dark Bluish Grey');
  });

  it('closes on Escape without changing anything', async () => {
    const onChange = vi.fn();
    render(<ColorField {...props({ value: 'bluish', onChange })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option').length).toBe(2));
    fireEvent.keyDown(field(), { key: 'Escape' });
    expect(screen.queryByRole('option')).toBeNull();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('opens the LDraw-only entries when all is checked', async () => {
    render(<ColorField {...props({ value: 'black' })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(1));
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() => expect(screen.getAllByRole('option')).toHaveLength(2));
  });

  it('offers nothing for a hex value, which needs no lookup', async () => {
    render(<ColorField {...props({ value: '#b40000' })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(field()).toBeTruthy());
    expect(screen.queryByRole('option')).toBeNull();
  });

  it('reports an emptied field as unset, the way every other row does', async () => {
    const onChange = vi.fn();
    render(<ColorField {...props({ value: 'Black', onChange })} />);
    fireEvent.change(field(), { target: { value: '' } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('still renders when the palette cannot be fetched', async () => {
    const dead = { colors: vi.fn().mockRejectedValue(new Error('no server')) } as unknown as LabClient;
    render(<ColorField {...props({ client: dead })} />);
    fireEvent.focus(field());
    await waitFor(() => expect(field()).toBeTruthy());
    expect(screen.queryByRole('option')).toBeNull();
  });
});
