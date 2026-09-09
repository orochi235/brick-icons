import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { LabClient } from '@lab/api/client';
import { IngestPage, duration, when } from '@lab/ingest/IngestPage';
import type { IngestAttempts, IngestRun } from '@lab/ingest/types';

const run = (over: Partial<IngestRun> = {}): IngestRun => ({
  id: 1, kind: 'store', started: '2026-09-08T20:43:19+00:00',
  finished: '2026-09-08T20:48:49+00:00', secs: 330, commit_sha: 'd0035fb',
  note: null, args: { dir: 'out/store' },
  counts: { stored: 7214, error: 6 }, total: 7220, ...over,
});

const attempts = (over: Partial<IngestAttempts> = {}): IngestAttempts => ({
  rows: [{ part_id: '3001', source: 'decal', state: 'stored', secs: 0.4,
           error: null, detail: null, prior: 'TimeoutError' }],
  errors: [], total: 1, kind: 'attempts', ...over,
});

function client(runs: IngestRun[], view: IngestAttempts = attempts()) {
  return {
    ingestRuns: vi.fn().mockResolvedValue(runs),
    ingestAttempts: vi.fn().mockResolvedValue(view),
  } as unknown as LabClient;
}

it('lists a run with its tally', async () => {
  render(<IngestPage client={client([run()])} />);
  expect(await screen.findByText('store')).toBeTruthy();
  expect(screen.getByText('7,214 stored')).toBeTruthy();
  expect(screen.getByText('6 error')).toBeTruthy();
  expect(screen.getByText('5m 30s')).toBeTruthy();
});

it('says so rather than showing an empty table when nothing was ingested', async () => {
  const c = client([run({ counts: {}, total: 0 })], attempts({ rows: [], total: 0 }));
  render(<IngestPage client={c} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  expect(await screen.findByText(/took nothing in/)).toBeTruthy();
});

it('reads a run\'s attempts only once it is opened', async () => {
  const c = client([run()]);
  render(<IngestPage client={c} />);
  await screen.findByText('store');
  expect(c.ingestAttempts).not.toHaveBeenCalled();
  fireEvent.click(screen.getByLabelText('run 1, store'));
  await waitFor(() => expect(c.ingestAttempts).toHaveBeenCalledWith(1, false));
  expect(await screen.findByText('3001')).toBeTruthy();
});

it('opens on Enter, because the row is not a button', async () => {
  const c = client([run()]);
  render(<IngestPage client={c} />);
  const row = await screen.findByLabelText('run 1, store');
  fireEvent.keyDown(row, { key: 'Enter' });
  await waitFor(() => expect(c.ingestAttempts).toHaveBeenCalled());
});

it('shows the error rollup rather than a row per casualty', async () => {
  const view = attempts({
    rows: [], errors: [{ error: 'ProcessDied', n: 400 }], total: 400 });
  render(<IngestPage client={client([run()], view)} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  expect(await screen.findByText('ProcessDied')).toBeTruthy();
  expect(screen.getByText('400')).toBeTruthy();
});

it('says how much of a capped list it is showing', async () => {
  const view = attempts({ total: 7220 });
  render(<IngestPage client={client([run()], view)} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  expect(await screen.findByText('1 of 7,220 shown')).toBeTruthy();
});

it('re-reads narrowed to the failures', async () => {
  const c = client([run()]);
  render(<IngestPage client={c} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  fireEvent.click(await screen.findByLabelText('failures only'));
  await waitFor(() => expect(c.ingestAttempts).toHaveBeenCalledWith(1, true));
});

it('formats a duration by the scale it is on', () => {
  expect(duration(null)).toBe('open');
  expect(duration(0.42)).toBe('0.4s');
  expect(duration(42)).toBe('42s');
  expect(duration(330)).toBe('5m 30s');
  expect(duration(12130)).toBe('3h 22m');
});

it('drops the date from a timestamp written today', () => {
  const now = new Date('2026-09-08T22:00:00Z');
  expect(when('2026-09-08T20:43:19Z', now)).not.toMatch(/Sep/);
  expect(when('2026-09-01T20:43:19Z', now)).toMatch(/Sep/);
});

it('says what each part was before this run touched it', async () => {
  render(<IngestPage client={client([run()])} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  // The row is read for what CHANGED: this part had been timing out and this
  // run stored it.
  expect(await screen.findByText('TimeoutError')).toBeTruthy();
  expect(screen.getByText('stored')).toBeTruthy();
});

it('calls a part this run met first never tried, not blank', async () => {
  const c = client([run()], attempts({
    rows: [{ part_id: '3002', source: 'occt', state: 'stored', secs: 1,
             error: null, detail: null, prior: null }],
  }));
  render(<IngestPage client={c} />);
  fireEvent.click(await screen.findByLabelText('run 1, store'));
  expect(await screen.findByText('never tried')).toBeTruthy();
});
