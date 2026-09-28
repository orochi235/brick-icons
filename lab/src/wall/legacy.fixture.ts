import {
  compile, DEFAULT_APPEARANCE, derive, type Facts, type PaintInput, type Palette
} from 'pezlie';
import type { PaintInput as LegacyInput } from '@lab/corpus/paint';
import type { Cell } from '@lab/corpus/types';
import { BRICK_ICONS } from './spec';

export const compiled = compile(BRICK_ICONS);

const derived = new WeakMap<readonly Cell[], Facts<Cell>>();

export function factsFor(cells: readonly Cell[]): Facts<Cell> {
  let facts = derived.get(cells);
  if (!facts) {
    facts = derive(compiled, cells);
    derived.set(cells, facts);
  }
  return facts;
}

function palette(legacy: LegacyInput['palette']): Palette {
  const { caret, label, sublabel, unmatched } = legacy;
  const states = Object.fromEntries(compiled.states.map((s) => [s.key, legacy[s.key as keyof typeof legacy]]));
  return { states, caret, label, sublabel, unmatched } as Palette;
}

/** The same frame asked of the new wall. */
export function translate(input: LegacyInput): PaintInput<Cell> {
  const a = input.appearance;
  return {
    compiled,
    facts: factsFor(input.cells),
    rect: (i) => input.rects[i],
    visible: input.visible,
    cam: input.cam,
    manifest: input.manifest,
    palette: palette(input.palette),
    loose: input.loose,
    vector: input.vector,
    highlight: input.highlight,
    highlightTag: input.highlightTag,
    stale: input.stale,
    caret: input.caret,
    bands: input.bands,
    tint: input.tint,
    gradient: input.gradient,
    // The legacy wall still shows badges from 56px.
    badgeMinPx: 56,
    appearance: a ? {
      thickBorderFactor: a.thickBorderFactor, thinBorderFactor: a.thinBorderFactor,
      maxBorderPx: a.maxBorderPx, dimAlpha: a.dimAlpha,
      showBadges: a.showBadges, showCaptions: a.showCaptions,
      wash: a.washRetired, washStrength: a.retiredWash,
    } : DEFAULT_APPEARANCE,
  };
}
