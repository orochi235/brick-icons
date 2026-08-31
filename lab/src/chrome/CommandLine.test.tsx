import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommandLine } from '@lab/chrome/CommandLine';
import type { LabClient } from '@lab/api/client';

const client = (command: string) => ({
  command: vi.fn(async () => ({ argv: command.split(' ').slice(1), command })),
} as unknown as LabClient);

describe('CommandLine', () => {
  it('shows the command the server reports', async () => {
    render(<CommandLine client={client('brick-icons 3941 --engine occt')}
      part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() =>
      expect(screen.getByText('brick-icons 3941 --engine occt')).toBeTruthy());
  });

  it('shows nothing to run when no part is chosen', () => {
    const api = client('');
    render(<CommandLine client={api} part="" config={{}} />);
    expect(api.command).not.toHaveBeenCalled();
    expect(screen.getByText(/no part/i)).toBeTruthy();
  });

  it('asks the server again when the config changes', async () => {
    const api = client('brick-icons 3941');
    const { rerender } = render(
      <CommandLine client={api} part="3941" config={{ engine: 'naive' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(1));
    rerender(<CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(2));
  });

  it('does not ask again when nothing changed', async () => {
    const api = client('brick-icons 3941');
    const { rerender } = render(
      <CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(api.command).toHaveBeenCalledTimes(1));
    rerender(<CommandLine client={api} part="3941" config={{ engine: 'occt' }} />);
    expect(api.command).toHaveBeenCalledTimes(1);
  });
});
