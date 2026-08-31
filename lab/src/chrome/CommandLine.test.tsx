import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CommandLine } from '@lab/chrome/CommandLine';
import type { LabClient } from '@lab/api/client';

const client = (command: string) => ({
  command: vi.fn(async () => ({ argv: command.split(' ').slice(1), command })),
} as unknown as LabClient);

describe('CommandLine', () => {
  it('collapses to the part id, since the argv is 20 flags long', async () => {
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    expect(container.querySelector('.command-line')!.textContent).toBe('3941');
    expect(screen.queryByText(/--engine occt/)).toBeNull();
  });

  it('opens the full command on hover', async () => {
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    fireEvent.pointerEnter(container.querySelector('.command-line')!);
    expect(screen.getByText('brick-icons 3941 --engine occt')).toBeTruthy();
  });

  it('opens it on a tap too, which a touch screen never hovers', async () => {
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    fireEvent.click(container.querySelector('.command-line')!);
    expect(screen.getByText('brick-icons 3941 --engine occt')).toBeTruthy();
  });

  it('closes again when the pointer leaves', async () => {
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    fireEvent.pointerEnter(container.querySelector('.command-line')!);
    fireEvent.pointerLeave(container.querySelector('.command-callout')!.parentElement!);
    expect(screen.queryByText('brick-icons 3941 --engine occt')).toBeNull();
  });

  it('a tap-opened callout survives the pointer leaving', async () => {
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    fireEvent.click(container.querySelector('.command-line')!);
    fireEvent.pointerLeave(container.querySelector('.command-callout')!.parentElement!);
    expect(screen.getByText('brick-icons 3941 --engine occt')).toBeTruthy();
  });

  it('copies the whole command, not the part id', async () => {
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText }, configurable: true,
    });
    const { container } = render(
      <CommandLine client={client('brick-icons 3941 --engine occt')}
        part="3941" config={{ engine: 'occt' }} />);
    await waitFor(() => expect(container.querySelector('.command-line')).toBeTruthy());
    fireEvent.click(container.querySelector('.command-line')!);
    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect(writeText).toHaveBeenCalledWith('brick-icons 3941 --engine occt');
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
