import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { Lightbox } from '@lab/corpus/Lightbox';

const detail = {
  part: { id: '3001', title: 'Brick 2 x 4', category: 'Brick', family: null,
          status: 'good', status_note: null },
  findings: [{ part_id: '3001', engine: 'naive', extra_d99: 1.5,
               missing_px: 3, secs: 12.0, error: null }],
  runs: [{ id: 7, kind: 'census', started: '2026-09-05T10:00:00+00:00',
           commit_sha: 'abc1234', engine: 'naive', extra_d99: 1.5,
           missing_px: 3, secs: 12.0, error: null }],
  defects: [{ id: 'd1', part: '3001', title: 'rim nubs', status: 'open' }],
  slots: [
    { source: 'silhouette-occt', sha256: 'cafebabe0000', made_at: '2026-09-05T10:00:00+00:00' },
    { source: 'naive', sha256: 'deadbeef0000', made_at: '2026-09-05T11:00:00+00:00' },
  ],
  features: { stud: null, elliptical: null, tris: 384, 'skew-deg': 0 },
};

const addDefect = vi.fn(async (r: unknown) => r);
const client = { corpusPart: () => Promise.resolve(detail), addDefect } as any;
const box = (props: Record<string, unknown> = {}) => (
  <Lightbox partId="3001" source="naive" client={client} onClose={() => {}}
            {...props} />
);

it('shows the part title and the part as every slot drew it', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const srcs = screen.getAllByRole('img', { name: /3001/ })
    .map((img) => img.getAttribute('src'));
  expect(srcs).toEqual([
    '/api/corpus/render/silhouette-occt/3001.svg?v=cafebabe',
    '/api/corpus/render/naive/3001.svg?v=deadbeef',
  ]);
});

it('marks which of the slots the wall is showing', async () => {
  // Queried off the document, not the render container: the panel is
  // portaled to the theme root so it can cover the shell's header.
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const current = document.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['naive']);
});

it('picks a different slot without the wall having moved', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'silhouette-occt' }));
  const current = document.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['silhouette-occt']);
});

it('shift-clicking a render opens it in a new tab instead of picking it', async () => {
  const open = vi.spyOn(window, 'open').mockImplementation(() => null);
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'silhouette-occt' }), { shiftKey: true });
  expect(open).toHaveBeenCalledWith(
    '/api/corpus/render/silhouette-occt/3001.svg?v=cafebabe', '_blank', 'noopener');
  const current = document.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['naive']);
  open.mockRestore();
});

it('files a flag against the slot you picked, not the wall\'s', async () => {
  addDefect.mockClear();
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'silhouette-occt' }));
  fireEvent.click(screen.getByText('Flag a problem'));
  fireEvent.change(screen.getByLabelText('What is wrong'),
                   { target: { value: 'the near rim is a whole circle' } });
  expect(screen.getByText('File against silhouette-occt')).toBeTruthy();
  fireEvent.click(screen.getByText('File against silhouette-occt'));
  await waitFor(() => expect(addDefect).toHaveBeenCalled());
  expect(addDefect.mock.calls[0]?.[0]).toMatchObject({ engines: ['occt'] });
});

it('follows the wall again when the wall changes slot', async () => {
  const { rerender } = render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'silhouette-occt' }));
  rerender(box({ source: 'silhouette-occt' }));
  rerender(box({ source: 'naive' }));
  const current = document.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['naive']);
});

it('lists each engine measurement', async () => {
  render(box());
  await waitFor(() => screen.getByText('1.5'));
});

it('lists open defects', async () => {
  render(box());
  await waitFor(() => screen.getByText('rim nubs'));
});

it('closes on the button', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.click(screen.getByLabelText('Close'));
  expect(onClose).toHaveBeenCalled();
});

it('closes on Escape', async () => {
  const onClose = vi.fn();
  render(box({ onClose }));
  await waitFor(() => screen.getByLabelText('Close'));
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(onClose).toHaveBeenCalled();
});

it('focuses the Close button on mount', async () => {
  render(box());
  await waitFor(() => screen.getByLabelText('Close'));
  expect(document.activeElement).toBe(screen.getByLabelText('Close'));
});

it('links the part out to the public catalogs, each in a new window', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const rebrickable = screen.getByRole('link', { name: 'Rebrickable' });
  expect(rebrickable.getAttribute('href')).toBe('https://rebrickable.com/parts/3001/');
  expect(rebrickable.getAttribute('target')).toBe('_blank');
  expect(rebrickable.getAttribute('rel')).toContain('noopener');
  expect(screen.getByRole('link', { name: 'BrickLink' }).getAttribute('href'))
    .toBe('https://www.bricklink.com/v2/catalog/catalogitem.page?P=3001');
});

it('links the part into the lab, in its own tab', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const link = screen.getByRole('link', { name: 'Open in lab' });
  expect(link.getAttribute('href')).toBe('/index.html?part=3001');
  expect(link.getAttribute('target')).toBe('_blank');
});

it('files a defect against the slot being viewed', async () => {
  addDefect.mockClear();
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('button', { name: 'Flag a problem' }));
  fireEvent.change(screen.getByLabelText('What is wrong'),
                   { target: { value: 'the rim is drawn whole' } });
  fireEvent.click(screen.getByRole('button', { name: /File against/ }));
  await waitFor(() => expect(addDefect).toHaveBeenCalled());
  expect(addDefect.mock.calls[0]![0]).toMatchObject({
    id: '3001-the-rim-is-drawn-whole',
    part: '3001',
    engines: ['naive'],
    status: 'open',
    title: 'the rim is drawn whole',
  });
});

it('marks each slot with the state the wall would color its cell', async () => {
  const detailed = {
    ...detail,
    part: { ...detail.part, out_of_scope: false },
    slots: [
      { ...detail.slots[0], error: 'TimeoutError', open_defects: 0,
        review_defects: 0, accepted_defects: 0, elsewhere: [] },
      { ...detail.slots[1], error: null, open_defects: 2,
        review_defects: 0, accepted_defects: 0, elsewhere: [] },
    ],
  };
  render(box({ client: { corpusPart: () => Promise.resolve(detailed), addDefect } }));
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const states = [...document.querySelectorAll('.corpus-slot')]
    .map((el) => el.getAttribute('data-state'));
  expect(states).toEqual(['timeout', 'defect']);
});

it('leaves a slot from an API older than the state fields unmarked', async () => {
  // Every slot listed has a render, so the honest state for one that says
  // nothing is the clean one -- not a defect the server never claimed.
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const states = [...document.querySelectorAll('.corpus-slot')]
    .map((el) => el.getAttribute('data-state'));
  expect(states).toEqual(['unknown', 'unknown']);
});

it('says what the part is built from', async () => {
  render(box());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  expect(screen.getByText('elliptical')).toBeTruthy();
  expect(screen.getByText('384')).toBeTruthy();
});

it('survives an API too old to send the features', async () => {
  const { features, ...older } = detail;
  const stale = { corpusPart: () => Promise.resolve(older), addDefect } as any;
  render(box({ client: stale }));
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  expect(document.querySelector('.corpus-built')).toBeNull();
});

// --- closing a defect out, and judging one that has been redrawn -----------

const reviewDetail = (over: Record<string, unknown> = {}) => ({
  ...detail,
  defects: [{ id: 'd1', part: '3001', title: 'rim nubs', status: 'open',
              engines: ['naive'], checked: { naive: 'stale-sha' }, ...over }],
});

const withDefects = (d: ReturnType<typeof reviewDetail>) => {
  const patchDefect = vi.fn(
    async (_id: string, _changes: Record<string, unknown>) => ({}));
  return {
    patchDefect,
    client: { corpusPart: () => Promise.resolve(d), addDefect, patchDefect } as any,
  };
};

it('closes a defect out from the panel the render is in', async () => {
  const { client: c, patchDefect } = withDefects(reviewDetail({ checked: undefined }));
  render(box({ client: c }));
  await waitFor(() => screen.getByText('rim nubs'));
  fireEvent.change(screen.getByLabelText('status of rim nubs'),
                   { target: { value: 'fixed' } });
  await waitFor(() => expect(patchDefect).toHaveBeenCalled());
  expect(patchDefect.mock.calls[0]![0]).toBe('d1');
  expect(patchDefect.mock.calls[0]![1]).toMatchObject({ status: 'fixed' });
});

it('offers a verdict only on a defect whose slot has been redrawn', async () => {
  const { client: c } = withDefects(reviewDetail());
  render(box({ client: c }));
  await waitFor(() => screen.getByText('rim nubs'));
  // `naive` now draws deadbeef0000; the defect was judged against stale-sha.
  expect(screen.getByRole('button', { name: 'fixed' })).toBeTruthy();
  expect(screen.getByRole('button', { name: 'still broken' })).toBeTruthy();
});

it('leaves a defect judged against the render on screen alone', async () => {
  const { client: c } = withDefects(reviewDetail({ checked: { naive: 'deadbeef0000' } }));
  render(box({ client: c }));
  await waitFor(() => screen.getByText('rim nubs'));
  expect(screen.queryByRole('button', { name: 'still broken' })).toBeNull();
});

// Without the re-stamp, one look at a redrawn fault would leave it asking
// for review for good.
it('re-stamps the render it was judged against when it stays open', async () => {
  const { client: c, patchDefect } = withDefects(reviewDetail());
  render(box({ client: c }));
  await waitFor(() => screen.getByText('rim nubs'));
  fireEvent.click(screen.getByRole('button', { name: 'still broken' }));
  await waitFor(() => expect(patchDefect).toHaveBeenCalled());
  expect(patchDefect.mock.calls[0]![1]).toEqual({
    status: 'open', checked: { naive: 'deadbeef0000' },
  });
});

it('stamps a freshly filed defect with the render it was filed against', async () => {
  const { client: c } = withDefects(reviewDetail());
  render(box({ client: c }));
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('button', { name: /flag a problem/i }));
  fireEvent.change(screen.getByLabelText(/what is wrong/i),
                   { target: { value: 'the rim is doubled' } });
  fireEvent.click(screen.getByRole('button', { name: /file against/i }));
  await waitFor(() => expect(addDefect).toHaveBeenCalled());
  const filed = addDefect.mock.calls.at(-1)![0] as { checked: unknown };
  expect(filed.checked).toEqual({ naive: 'deadbeef0000' });
});

// --- a slot that never drew ------------------------------------------------

const failedDetail = {
  ...detail,
  part: { ...detail.part, out_of_scope: false },
  slots: [
    { source: 'occt', sha256: null, made_at: null, secs: 120.5,
      error: 'TimeoutError', open_defects: 0, review_defects: 0,
      accepted_defects: 0, elsewhere: [] },
    { ...detail.slots[1], secs: 12, error: null, open_defects: 0,
      review_defects: 0, accepted_defects: 0, elsewhere: [] },
  ],
};
const failedBox = (props: Record<string, unknown> = {}) => box({
  client: { corpusPart: () => Promise.resolve(failedDetail), addDefect },
  ...props,
});

it('gives a slot that never drew a tile saying why', async () => {
  render(failedBox());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  const tile = document.querySelector('.corpus-slot[data-state="timeout"]')!;
  expect(tile.querySelector('img')).toBeNull();
  expect(tile.textContent).toContain('TimeoutError');
  expect(tile.textContent).toContain('120.5s');
});

it('says a slot was never run rather than leaving the tile blank', async () => {
  const never = {
    ...failedDetail,
    slots: [{ ...failedDetail.slots[0], secs: null, error: null }],
  };
  render(box({ client: { corpusPart: () => Promise.resolve(never), addDefect } }));
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  expect(document.querySelector('.corpus-slot-empty')!.textContent)
    .toContain('not drawn');
});

it('lets a slot with no render still be picked', async () => {
  render(failedBox());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'occt' }));
  const current = document.querySelectorAll('[data-current="true"] .corpus-slot-name');
  expect([...current].map((el) => el.textContent)).toEqual(['occt']);
});

it('has no render to open for a slot that never drew', async () => {
  const open = vi.spyOn(window, 'open').mockImplementation(() => null);
  render(failedBox());
  await waitFor(() => screen.getByText('Brick 2 x 4'));
  fireEvent.click(screen.getByRole('radio', { name: 'occt' }), { shiftKey: true });
  expect(open).not.toHaveBeenCalled();
  open.mockRestore();
});
