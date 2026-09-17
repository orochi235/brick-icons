import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { LabClient } from '@lab/api/client';
import { ReviewPage, rowsFor } from '@lab/review/ReviewPage';
import type { ReviewEntry, ReviewList, ReviewSide } from '@lab/review/types';

const side = (over: Partial<ReviewSide> = {}): ReviewSide => ({
  path: 'out/a/renders/occt/3001.svg', sha256: 'a'.repeat(64),
  made_at: '2026-09-10T11:15:37+00:00', run_id: 1, build: '100.aaa1111',
  secs: 1.5, extra_d99: 0.41, missing_px: 120, error: null,
  edge: { declared_len: 2259.5, missing_len: 184, missing_comps: 3 }, ...over,
});

const entry = (over: Partial<ReviewEntry> = {}): ReviewEntry => ({
  id: 'occt/3001/bbbbbbbbbbbb', part: '3001', title: 'Brick 2 x 4',
  source: 'occt', engine: 'occt', at: '2026-09-16T05:46:36+00:00', run_id: 2,
  by: 'slot-occt-refresh',
  before: side(),
  after: side({ path: 'out/b/renders/occt/3001.svg', sha256: 'b'.repeat(64),
                run_id: 2, build: '101.bbb2222', secs: 1.2, extra_d99: 0.3 }),
  diff: { components: 3, pixels: 1961, width: 900, at: '2026-09-16T06:00:00+00:00' },
  defects: [{ id: '3001-occt-rim', title: 'rim missing', status: 'open',
              checked: 'a'.repeat(64) }],
  request: null, judged: null, superseded_by: null,
  urls: { before: '/api/review/occt/3001/bbbbbbbbbbbb/before',
          after: '/api/review/occt/3001/bbbbbbbbbbbb/after',
          diff: '/api/review/occt/3001/bbbbbbbbbbbb/diff.png' },
  ...over,
});

const list = (entries: ReviewEntry[], over: Partial<ReviewList> = {}): ReviewList => ({
  entries, total: entries.length, view: 'linked',
  verdicts: ['fixed', 'better', 'neutral', 'regression'], ...over,
});

function client(entries: ReviewEntry[]) {
  const review = vi.fn().mockResolvedValue(list(entries));
  const judge = vi.fn().mockImplementation(async (id: string, verdict: string, note: string) => ({
    ...entries.find((e) => e.id === id)!,
    judged: { verdict, note, at: '2026-09-17T00:00:00+00:00', by: 'lab', defects: ['3001-occt-rim'] },
  }));
  return {
    client: { review, judge, reviewEntry: vi.fn(), measureReview: vi.fn() } as unknown as LabClient,
    review, judge,
  };
}

it('shows a card with its three panels, both columns and the linked defect', async () => {
  render(<ReviewPage client={client([entry()]).client} />);
  expect(await screen.findByText('Brick 2 x 4')).toBeTruthy();
  expect(screen.getByAltText('3001 before')).toBeTruthy();
  expect(screen.getByAltText('3001 after')).toBeTruthy();
  expect(screen.getByAltText('3001 diff')).toBeTruthy();
  expect(screen.getByText(/3 components/)).toBeTruthy();
  expect(screen.getByText('100.aaa1111')).toBeTruthy();
  expect(screen.getByText('101.bbb2222')).toBeTruthy();
  expect(screen.getByText('rim missing')).toBeTruthy();
  expect(screen.getByText('judged against before')).toBeTruthy();
  expect(screen.getByText('1 of 1 shown')).toBeTruthy();
});

it('posts a verdict with the note and drops the card from the waiting list', async () => {
  const c = client([entry()]);
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.change(screen.getByLabelText('note for 3001'), { target: { value: 'rim is back' } });
  fireEvent.click(screen.getByRole('button', { name: /^fixed/ }));
  await waitFor(() => expect(c.judge).toHaveBeenCalledWith('occt/3001/bbbbbbbbbbbb', 'fixed', 'rim is back'));
  await waitFor(() => expect(screen.queryByText('Brick 2 x 4')).toBeNull());
  expect(screen.getByText('0 of 0 shown')).toBeTruthy();
});

it('keeps a judged card, showing its verdict, when judged cards are shown', async () => {
  const c = client([entry()]);
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.click(screen.getByLabelText('show judged'));
  await waitFor(() => expect(c.review).toHaveBeenLastCalledWith('linked', 1, true));
  fireEvent.click(screen.getByRole('button', { name: /^regression/ }));
  expect(await screen.findByText('regression', { selector: 'strong' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /^fixed/ })).toBeNull();
});

it('a verdict key judges the focused card', async () => {
  const c = client([entry(), entry({ id: 'occt/3002/cccccccccccc', part: '3002', title: 'Brick 2 x 3' })]);
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 3');
  fireEvent.keyDown(window, { key: 'j' });
  fireEvent.keyDown(window, { key: 'n' });
  await waitFor(() => expect(c.judge).toHaveBeenCalledWith('occt/3002/cccccccccccc', 'neutral', ''));
});

it('the all view asks with its bar, and offers to measure what has none', async () => {
  const c = client([entry({ diff: null, defects: [] })]);
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.click(screen.getByRole('button', { name: 'All changes' }));
  await waitFor(() => expect(c.review).toHaveBeenLastCalledWith('all', 1, false));
  fireEvent.change(screen.getByLabelText('minimum components'), { target: { value: '5' } });
  await waitFor(() => expect(c.review).toHaveBeenLastCalledWith('all', 5, false));
  expect(screen.getByText(/measuring…/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'measure 1 of 1 unmeasured' })).toBeTruthy();
});

it('says when the slot has moved on', async () => {
  render(<ReviewPage client={client([entry({ superseded_by: 'occt/3001/dddddddddddd' })]).client} />);
  expect(await screen.findByText(/drawn this part again/)).toBeTruthy();
});

it('rowsFor drops rows both sides leave empty and keeps the ones that differ', () => {
  const rows = rowsFor(side(), side({ secs: null, extra_d99: null, missing_px: null,
                                        edge: null, error: 'TimeoutError' }));
  const labels = rows.map(([label]) => label);
  expect(labels).toContain('error');
  expect(labels).toContain('secs');
  expect(rows.find(([label]) => label === 'edge gap')).toEqual(['edge gap', '184.0 of 2259.5', '']);
  expect(rowsFor(side({ error: null }), side({ error: null })).map(([l]) => l)).not.toContain('error');
});
