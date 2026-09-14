import { describe, expect, it } from 'vitest';
import { compile } from '@pezlie/wall/src/cel';
import { derive } from '@pezlie/wall/src/derive';
import type { Laid, Layout } from '@pezlie/wall/src/layout';
import { COVERAGE_ORDER } from '@lab/corpus/facts';
import type { Cell } from '@lab/corpus/types';
import { byCategory, GROUPINGS, SPEC } from '@lab/wall/host';

const cell = (index: number, over: Partial<Cell> = {}): Cell => ({
  id: `p${index}`, index, title: 'Brick', category: 'Brick', family: null,
  printed: false, obsolete: false, base: true, out_of_scope: false, moved: false,
  year_from: null, year_to: null, sets: null, colors: null, tags: [],
  status: 'unreviewed', sha: null, made_at: null, extra_d99: null, secs: null,
  error: null, open_defects: 0, review_defects: 0, accepted_defects: 0,
  elsewhere: [],
  ...over,
});

const compiled = compile(SPEC);
const opts = { cell: 10, gap: 0, cols: 40 };

function lay(cells: Cell[], layout: Layout<Cell>, rows = cells.map((_, i) => i)): Laid {
  return layout({ rows: Uint32Array.from(rows), facts: derive(compiled, cells) }, opts);
}
const outerKeys = (laid: Laid) => laid.bands.filter((b) => b.depth === 0).map((b) => b.key);
const grouping = (key: string) => GROUPINGS.find((g) => g.key === key)!;

describe('the wall groupings', () => {
  it('folds a category with too few parts on the wall into Other', () => {
    const cells = [
      ...Array.from({ length: 25 }, (_, i) => cell(i)),
      cell(25, { category: 'Plate' }), cell(26, { category: 'Plate' }),
    ];
    expect(outerKeys(lay(cells, byCategory))).toEqual(['Brick', 'Other']);
  });

  it('counts only the parts on the wall, not the whole corpus', () => {
    const cells = Array.from({ length: 60 },
      (_, i) => cell(i, { category: i < 30 ? 'Brick' : 'Plate' }));
    expect(outerKeys(lay(cells, byCategory))).toEqual(['Brick', 'Plate']);
    const fewPlates = [...Array.from({ length: 30 }, (_, i) => i), 30, 31, 32];
    expect(outerKeys(lay(cells, byCategory, fewPlates))).toEqual(['Brick', 'Other']);
  });

  it('keeps every coverage group in the order the dashboard uses', () => {
    const cells = [cell(0, { coverage: 'failed' }), cell(1, { coverage: 'drawn' })];
    expect(outerKeys(lay(cells, grouping('coverage').layout(false)))).toEqual(COVERAGE_ORDER);
  });

  it('bands releases by decade newest first, with unknown years last', () => {
    const cells = [cell(0, { year_from: 1978 }), cell(1, { year_from: 1995 }),
                   cell(2, { year_from: 1999 }), cell(3)];
    expect(outerKeys(lay(cells, grouping('release').layout(true))))
      .toEqual(['1990s', '1970s', 'unknown']);
  });
});
