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
          diff: '/api/review/occt/3001/bbbbbbbbbbbb/diff.png',
          reference: '/api/review/occt/3001/bbbbbbbbbbbb/reference' },
  ...over,
});

const list = (entries: ReviewEntry[], over: Partial<ReviewList> = {}): ReviewList => ({
  entries, total: entries.length, hidden: 0, superseded: 0, view: 'linked',
  verdicts: ['fixed', 'better', 'neutral', 'regression'], ...over,
});

function client(entries: ReviewEntry[]) {
  const review = vi.fn().mockResolvedValue(list(entries));
  const judge = vi.fn().mockImplementation(async (id: string, verdict: string, note: string) => ({
    ...entries.find((e) => e.id === id)!,
    judged: { verdict, note, at: '2026-09-17T00:00:00+00:00', by: 'lab', defects: ['3001-occt-rim'] },
  }));
  const undoJudgement = vi.fn().mockImplementation(async (id: string) => ({
    ...entries.find((e) => e.id === id)!, judged: null, restored: true,
  }));
  return {
    client: { review, judge, reviewEntry: vi.fn(), measureReview: vi.fn(),
              undoJudgement } as unknown as LabClient,
    review, judge, undoJudgement,
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

it('posts a verdict with the note and marks the card judged in place', async () => {
  const c = client([entry()]);
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.change(screen.getByLabelText('note for 3001'), { target: { value: 'rim is back' } });
  fireEvent.click(screen.getByRole('button', { name: /^fixed/ }));
  await waitFor(() => expect(c.judge).toHaveBeenCalledWith('occt/3001/bbbbbbbbbbbb', 'fixed', 'rim is back'));
  // The card holds its place rather than vanishing, or the undo it just
  // earned would be unreachable without ticking "show judged".
  await waitFor(() => expect(screen.getByText('rim is back')).toBeTruthy());
  expect(screen.getByText('Brick 2 x 4')).toBeTruthy();
  expect(screen.queryByLabelText('note for 3001')).toBeNull();
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

it('shows the reference panel from the corpus reference slot', async () => {
  render(<ReviewPage client={client([entry()]).client} />);
  const img = await screen.findByAltText('3001 reference') as HTMLImageElement;
  expect(img.getAttribute('src')).toBe('/api/review/occt/3001/bbbbbbbbbbbb/reference');
  expect(screen.getByText(/reference · LDView/)).toBeTruthy();
});

it('keeps a judged card in place so its undo is reachable', async () => {
  const { client: c } = client([entry()]);
  render(<ReviewPage client={c} />);
  fireEvent.click(await screen.findByText(/^fixed/));
  await waitFor(() => expect(screen.getByText('undo')).toBeTruthy());
  expect(screen.getByText('Brick 2 x 4')).toBeTruthy();
  expect(screen.getByText(/1 judged/)).toBeTruthy();
});

it('undoes a verdict from the button and puts the card back in the queue', async () => {
  const { client: c, undoJudgement } = client([entry()]);
  render(<ReviewPage client={c} />);
  fireEvent.click(await screen.findByText(/^fixed/));
  fireEvent.click(await screen.findByText('undo'));
  await waitFor(() => expect(undoJudgement).toHaveBeenCalledWith('occt/3001/bbbbbbbbbbbb'));
  await waitFor(() => expect(screen.queryByText('undo')).toBeNull());
});

it('undoes the focused card on the u key, and ignores it when unjudged', async () => {
  const { client: c, undoJudgement } = client([entry()]);
  render(<ReviewPage client={c} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.keyDown(window, { key: 'u' });
  expect(undoJudgement).not.toHaveBeenCalled();
  fireEvent.keyDown(window, { key: 'f' });
  await waitFor(() => expect(screen.getByText('undo')).toBeTruthy());
  fireEvent.keyDown(window, { key: 'u' });
  await waitFor(() => expect(undoJudgement).toHaveBeenCalledOnce());
});

it('says so when a verdict was too old to restore', async () => {
  const { client: c, undoJudgement } = client([entry()]);
  undoJudgement.mockResolvedValue({ ...entry(), judged: null, restored: false });
  render(<ReviewPage client={c} />);
  fireEvent.click(await screen.findByText(/^fixed/));
  fireEvent.click(await screen.findByText('undo'));
  expect(await screen.findByText(/previous checked sha is gone/)).toBeTruthy();
});

it('says how many unchanged redraws the screen hid, and can show them', async () => {
  const c = client([entry()]);
  c.review.mockResolvedValue(list([entry()], { hidden: 20 }));
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  expect(screen.getByText(/20 unchanged, hidden/)).toBeTruthy();
  await waitFor(() => expect(c.review).toHaveBeenCalledWith('linked', 1, false));
  fireEvent.click(screen.getByLabelText('show unchanged'));
  await waitFor(() => expect(c.review).toHaveBeenCalledWith('linked', 0, false));
});

it('measures the linked entries the screen cannot weigh yet', async () => {
  const c = client([entry({ diff: null })]);
  const measureReview = vi.fn().mockResolvedValue({ measured: 1, failed: [] });
  const withMeasure = { ...c.client, measureReview } as unknown as LabClient;
  render(<ReviewPage client={withMeasure} />);
  await screen.findByText('Brick 2 x 4');
  fireEvent.click(screen.getByRole('button', { name: /measure 1 of 1 unmeasured/ }));
  await waitFor(() => expect(measureReview).toHaveBeenCalledWith(50, 'linked'));
});

it('says how many earlier hops of a redrawn part the queue hid', async () => {
  const c = client([entry()]);
  c.review.mockResolvedValue(list([entry()], { superseded: 3 }));
  render(<ReviewPage client={c.client} />);
  await screen.findByText('Brick 2 x 4');
  expect(screen.getByText(/3 redrawn since, hidden/)).toBeTruthy();
});
