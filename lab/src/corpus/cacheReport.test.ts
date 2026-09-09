import { expect, it, vi } from 'vitest';
import { cacheReport, findings, probeCell, rungName } from '@lab/corpus/cacheReport';
import type { CacheReportInput } from '@lab/corpus/cacheReport';

const healthy: CacheReportInput = {
  slot: 'silhouette-occt',
  cellPx: 300,
  dpr: 2,
  level: 512,
  cells: { shown: 9000, visible: 20, visibleWithSha: 20 },
  sheets: [{ level: 8, loaded: true, version: 'v1', baked: 9000 },
           { level: 32, loaded: true, version: 'v1', baked: 9000 }],
  loose: { loaded: 40, requested: 40 },
  vector: { resident: 20, inFlight: 0, queued: 0, bytesCached: 20,
            rasterPx: [600] },
};

const only = (input: CacheReportInput) => findings(input).join(' | ');

it('says so plainly when nothing is wrong', () => {
  expect(findings(healthy)).toEqual([expect.stringContaining('nothing wrong')]);
});

it('names the rung in the words the code uses', () => {
  expect(rungName(8)).toBe('sheet-8');
  expect(rungName(32)).toBe('sheet-32');
  expect(rungName(128)).toBe('loose');
  expect(rungName(512)).toBe('vector');
});

it('catches a wall stuck on upscaled 128px thumbs', () => {
  // The symptom the button exists for: big cells, and the level never left
  // the last raster rung.
  const report = cacheReport({ ...healthy, level: 128 });
  expect(report.ladder).toMatchObject({ level: 128, wants: 512, rung: 'loose' });
  expect(only({ ...healthy, level: 128 }))
    .toContain('every cell is an upscaled 128px PNG');
});

it('catches a slot whose rows carry no hash', () => {
  // `wantedVector` and `wanted` both skip a cell with no sha, so neither
  // upper rung ever asks for anything and no error is raised anywhere.
  const blind = { ...healthy,
                  cells: { shown: 9000, visible: 20, visibleWithSha: 0 } };
  expect(only(blind)).toContain('no visible cell has a sha256');
  expect(cacheReport(blind).cells.visibleWithoutSha).toBe(20);
});

it('reports the pixel budget starving a big viewport', () => {
  const crowded = { ...healthy, cellPx: 512,
                    cells: { shown: 9000, visible: 400, visibleWithSha: 400 } };
  const report = cacheReport(crowded);
  expect(report.budget.starved).toBe(true);
  expect(only(crowded)).toContain('the pixel budget holds');
});

it('does not call the budget starved below the vector rung', () => {
  // Under 512 nothing is rasterized at all, so the cap is not the problem
  // and naming it would send the reader to the wrong rung.
  const report = cacheReport({ ...healthy, level: 32,
    cells: { shown: 9000, visible: 400, visibleWithSha: 400 } });
  expect(report.budget.starved).toBe(false);
});

it('catches the vector rung being idle when it should be working', () => {
  expect(only({ ...healthy,
    vector: { resident: 0, inFlight: 0, queued: 0, bytesCached: 0, rasterPx: [] } }))
    .toContain('the work is not being asked for at all');
});

it('catches loose thumbs that were all asked for and never arrived', () => {
  expect(only({ ...healthy, level: 128,
                loose: { loaded: 0, requested: 200 } }))
    .toContain('200 loose thumbs were requested and none loaded');
});

it('catches a sheet that never loaded', () => {
  expect(only({ ...healthy,
    sheets: [{ level: 8, loaded: false, version: null, baked: 0 },
             { level: 32, loaded: true, version: 'v1', baked: 9000 }] }))
    .toContain('sheet-8 never loaded');
});

it('surfaces the fetch status the wall swallows', () => {
  const probes = [{ id: '3001', url: '/api/corpus/render/occt/3001.svg',
                    status: 404, contentType: null, bytes: null, error: null }];
  expect(findings(healthy, probes).join(' | '))
    .toContain('the render URL answered 404');
});

it('surfaces the rasterize error the wall swallows', () => {
  const probes = [{ id: '3001', url: '/x.svg', status: 200,
                    contentType: 'image/svg+xml', bytes: 12,
                    error: 'no element found' }];
  expect(findings(healthy, probes).join(' | '))
    .toContain('failed to rasterize -- no element found');
});

it('probes a cell by walking the same two steps the rung does', async () => {
  const fetch = vi.fn(async () => new Response('nope', { status: 500 }));
  const probe = await probeCell('3001', '/api/x.svg', 512, { fetch } as never);
  expect(probe).toMatchObject({ id: '3001', status: 500, bytes: null });
  // A non-ok response is not rasterized, so it reports no parse error to
  // distract from the status.
  expect(probe.error).toBeNull();
});

it('reports a fetch that never answered', async () => {
  const fetch = vi.fn(async () => { throw new Error('Failed to fetch'); });
  const probe = await probeCell('3001', '/api/x.svg', 512, { fetch } as never);
  expect(probe.status).toBeNull();
  expect(probe.error).toBe('fetch: Failed to fetch');
});

it('refuses to report on a wall that has not drawn yet', () => {
  // cellPx is 0 until the first camera exists, and every other number is
  // then a fact about nothing.
  const cold = findings({ ...healthy, cellPx: 0, level: 32,
    cells: { shown: 0, visible: 0, visibleWithSha: 0 },
    sheets: [{ level: 8, loaded: false, version: null, baked: 0 }] });
  expect(cold).toEqual([expect.stringContaining('has not laid out yet')]);
});
