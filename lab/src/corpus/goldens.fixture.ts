import { gridLayout } from '@lab/corpus/layout';
import { DEFAULT_APPEARANCE, type PaintInput } from '@lab/corpus/paint';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import { TINT_MODES } from '@lab/corpus/tint';
import type { Cell, SheetManifest } from '@lab/corpus/types';

const cell = (id: string, index: number, overrides: Partial<Cell> = {}): Cell => ({
  id, index, title: `part ${id}`, category: 'Brick', family: null,
  printed: false, obsolete: false, base: true, out_of_scope: false, moved: false,
  year_from: 1978, year_to: 1994, sets: 42, colors: 9, tags: [],
  status: 'unreviewed', sha: `sha-${id}`, made_at: '2025-01-01T00:00:00Z',
  extra_d99: null, secs: 1.5, error: null,
  open_defects: 0, open_defects_elsewhere: 0, accepted_defects: 0,
  error_elsewhere: false, ...overrides,
});

// A slot that is out of scope, timed out or errored produced no thumbnail, so
// it carries no sha -- which is also what puts the fill paths in every
// scenario rather than only the stale one.
export const GOLDEN_CELLS: Cell[] = [
  cell('unknown', 0),
  cell('oos', 1, { out_of_scope: true, category: '_Sticker', sha: null }),
  cell('timeout', 2, { error: 'TimeoutError', sha: null }),
  cell('failed', 3, { error: 'RuntimeError', sha: null }),
  cell('defect', 4, { open_defects: 2 }),
  cell('accepted', 5, { accepted_defects: 1 }),
  cell('probelse', 6, { error_elsewhere: true }),
  cell('defelse', 7, { open_defects_elsewhere: 1 }),
  cell('retired', 8, { tags: ['retired'] }),
  cell('popular', 9, { tags: ['popular', 'technic'] }),
  cell('replaced', 10, { tags: ['replaced'], successor: '3002' }),
  cell('unrendered', 11, { sha: null }),
  cell('nodata', 12, { year_from: null, sets: null, colors: null }),
];

const SHEET = {
  level: 32, gutter: 2, pitch: 36, cols: 4, rows: 4,
  count: GOLDEN_CELLS.length, size: 144,
};

export const FRESH_MANIFEST: SheetManifest = {
  ...SHEET,
  baked: Object.fromEntries(
    GOLDEN_CELLS.filter((c) => c.sha !== null).map((c) => [c.id, c.sha as string]),
  ),
};

/** One entry behind the store and one gone altogether -- a lost sidecar entry
 *  reaches `isStale` differently from a stale one, and both drop the cell back
 *  to a fill. */
export const STALE_MANIFEST: SheetManifest = (() => {
  const baked: Record<string, string> =
    { ...FRESH_MANIFEST.baked, unknown: 'sha-unknown-older' };
  delete baked.defect;
  return { ...SHEET, baked };
})();

const CELL_SIZES = [8, 32, 64, 120, 200];
const GAP = 4;
const COLS = 4;

export function scenarios(): { name: string; input: PaintInput }[] {
  const out: { name: string; input: PaintInput }[] = [];
  for (const size of CELL_SIZES) {
    const { rects } = gridLayout(GOLDEN_CELLS, { cell: size, gap: GAP, cols: COLS });
    const base: PaintInput = {
      cells: GOLDEN_CELLS,
      rects,
      visible: GOLDEN_CELLS.map((_, i) => i),
      cam: { x: 0, y: 0, scale: { x: 1, y: 1 } },
      manifest: FRESH_MANIFEST,
      palette: DEFAULT_PALETTE,
      appearance: DEFAULT_APPEARANCE,
    };
    const variants: { name: string; input: PaintInput }[] = [
      { name: 'fresh', input: base },
      { name: 'stale', input: { ...base, manifest: STALE_MANIFEST } },
      { name: 'nobadges',
        input: { ...base,
                 appearance: { ...DEFAULT_APPEARANCE, showBadges: false,
                               showCaptions: false } } },
      { name: 'highlight-defect', input: { ...base, highlight: 'defect' } },
      { name: 'caret', input: { ...base, caret: 4 } },
      ...TINT_MODES.map((tint) => ({ name: `tint-${tint}`, input: { ...base, tint } })),
    ];
    for (const v of variants) out.push({ name: `px${size}-${v.name}`, input: v.input });
  }
  return out;
}
