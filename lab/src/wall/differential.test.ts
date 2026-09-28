import { describe, expect, it } from 'vitest';
import { applySelection, paintCommands, tally } from 'pezlie';
import { CLASS_SPECS, FILTER_SPECS, SORT_SPECS } from '@lab/corpus/criteria';
import { decadeOf, yearOf } from '@lab/corpus/facts';
import { bandedLayout } from '@lab/corpus/grouped';
import { gridLayout } from '@lab/corpus/layout';
import {
  DEFAULT_APPEARANCE, paintCommands as legacyPaint, tally as legacyTally,
  type PaintInput as LegacyInput,
} from '@lab/corpus/paint';
import { DEFAULT_PALETTE, LEGEND_STATES } from '@lab/corpus/palette';
import { applySelection as legacySelect, type Selection as LegacySelection } from '@lab/corpus/select';
import { TINT_MODES } from '@lab/corpus/tint';
import type { Cell } from '@lab/corpus/types';
import { generateCells, generateManifest } from './cells.fixture';
import { compiled, factsFor, translate } from './legacy.fixture';

const SEEDS = [1, 7, 2026];
const N = 300;
const SIZES = [8, 24, 56, 64, 88, 120, 200];

const serialize = (v: unknown) => JSON.stringify(v);

function frames(cells: Cell[], seed: number): { name: string; input: LegacyInput }[] {
  const manifest = generateManifest(seed, cells);
  const images = new Map(cells.filter((_, i) => i % 11 === 0).map((c) => [c.id, {} as HTMLImageElement]));
  const vectors = new Map(cells.filter((_, i) => i % 13 === 0).map((c) => [c.id, {} as CanvasImageSource]));
  const out: { name: string; input: LegacyInput }[] = [];
  for (const size of SIZES) {
    const grid = gridLayout(cells, { cell: size, gap: 4, cols: 12 });
    const banded = bandedLayout(decadeOf, yearOf, false)(cells, { cell: size, gap: 4, cols: 12 });
    const base: LegacyInput = {
      cells, rects: grid.rects, visible: cells.map((_, i) => i),
      cam: { x: 0, y: 0, scale: { x: 1, y: 1 } }, manifest, palette: DEFAULT_PALETTE,
      appearance: DEFAULT_APPEARANCE,
    };
    const add = (name: string, input: LegacyInput) => out.push({ name: `px${size}-${name}`, input });
    add('base', base);
    add('panned', { ...base, cam: { x: -37, y: -12, scale: { x: 1.5, y: 1.5 } },
                    visible: base.visible.filter((i) => i % 3 !== 0) });
    add('banded', { ...base, rects: banded.rects, bands: banded.bands });
    add('images', { ...base, loose: images, vector: vectors });
    add('no-manifest', { ...base, manifest: null });
    add('stale', { ...base, stale: true });
    add('caret', { ...base, caret: 5 });
    for (const showBadges of [true, false]) {
      for (const showCaptions of [true, false]) {
        for (const washRetired of [true, false]) {
          add(`appearance-${showBadges}-${showCaptions}-${washRetired}`,
              { ...base, appearance: { ...DEFAULT_APPEARANCE, showBadges, showCaptions, washRetired } });
        }
      }
    }
    for (const highlight of LEGEND_STATES) add(`highlight-${highlight}`, { ...base, highlight });
    for (const highlightTag of ['technic', 'unclaimed']) {
      add(`tag-${highlightTag}`, { ...base, highlightTag });
    }
    for (const tint of TINT_MODES) {
      for (const gradient of ['ember', 'viridis'] as const) {
        add(`tint-${tint}-${gradient}`, { ...base, tint, gradient });
      }
    }
  }
  return out;
}

describe.each(SEEDS)('seed %i', (seed) => {
  const cells = generateCells(seed, N);

  // Known drift: the legacy wall moved the family caption to `br` (b630f8a) and
  // added a "replaced by" caption line (bc592f0); the spec has neither yet.
  it.fails('paints every frame as the legacy wall does', () => {
    const differ: string[] = [];
    const all = frames(cells, seed);
    for (const { name, input } of all) {
      if (serialize(paintCommands(translate(input))) !== serialize(legacyPaint(input))) {
        differ.push(name);
      }
    }
    expect(differ, `${differ.length} of ${all.length} frames differ`).toEqual([]);
  });

  it('tallies states as the legacy wall does', () => {
    expect(tally(compiled, factsFor(cells))).toEqual(legacyTally(cells));
  });

  it('selects and orders as the legacy wall does', () => {
    const facts = factsFor(cells);
    const classKeys = CLASS_SPECS.map((c) => c.key);
    const shownSets = [
      Object.fromEntries(CLASS_SPECS.map((c) => [c.key, c.shown])),
      Object.fromEntries(classKeys.map((k) => [k, true])),
      Object.fromEntries(classKeys.map((k) => [k, false])),
      Object.fromEntries(classKeys.map((k, i) => [k, i % 2 === 0])),
    ];
    const differ: string[] = [];
    let count = 0;
    for (const sort of SORT_SPECS.map((s) => s.key)) {
      for (const filter of FILTER_SPECS.map((f) => f.key)) {
        for (const shown of shownSets) {
          for (const excluded of [[], ['Brick', '-']]) {
            for (const badges of [[], ['technic'], ['technic', 'duplo'], ['technic', 'printed'], ['unclaimed']]) {
              count++;
              const legacy: LegacySelection = {
                sort, filter, shown: shown as LegacySelection['shown'], grouping: 'none',
                tint: 'status', gradient: 'ember', excluded, badges, desc: false,
              };
              const want = legacySelect(cells, legacy).map((c) => c.id);
              const got = Array.from(applySelection(compiled, facts,
                { sort, filter, shown, exclude: { category: excluded }, tags: badges }),
                (row) => cells[row]!.id);
              if (serialize(got) !== serialize(want)) {
                differ.push(`${sort}/${filter}/${serialize(shown)}/${excluded}/${badges}`);
              }
            }
          }
        }
      }
    }
    expect(differ.slice(0, 5), `${differ.length} of ${count} selections differ`).toEqual([]);
  });
});
