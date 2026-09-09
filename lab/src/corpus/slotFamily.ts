/** The two things a slot name says at once, split apart so the toolbar can
 *  ask them separately: WHO drew it, and WHICH drawing.
 *
 *  A slot is `<facet>-<engine>` or a bare name, and the wall used to offer all
 *  eleven in one list -- so moving from naive's silhouette to occt's meant
 *  finding the other end of an alphabetical list. The family is the toggle,
 *  the facet is the dropdown. `db.SOURCES` is the list this covers. */
import { engineFor } from '@lab/corpus/flag';

/** Who drew it. `decal` is its own: it has no viewpoint and no engine flag --
 *  `unwrap` lays the artwork flat on its carrier -- so it is neither a
 *  reference nor a drawing either engine made. */
export type Family = 'reference' | 'legacy' | 'occt' | 'decal';

/** Toggle order, and it is not alphabetical or historical: occt is the engine
 *  under work, so it opens the row. */
export const FAMILY_ORDER: readonly Family[] = ['occt', 'legacy', 'reference', 'decal'];

export const FAMILY_LABEL: Record<Family, string> = {
  reference: 'Reference',
  legacy: 'Legacy',
  occt: 'OCCT',
  decal: 'Decal',
};

/** The bare slot's facet. `naive` and `occt` carry no qualifier because they
 *  are the canonical drawing -- flat3 shading with 2px strokes. */
export const BARE_FACET = 'flat3';

export function familyOf(source: string): Family {
  const engine = engineFor(source);
  if (engine === 'naive') return 'legacy';
  if (engine === 'occt') return 'occt';
  if (engine === 'decal') return 'decal';
  return 'reference';
}

/** What the dropdown shows for a slot, once its family is decided elsewhere.
 *  A reference slot has no facet -- `ldview` and `reference` differ by which
 *  renderer drew them, not by what was drawn -- so it keeps its whole name. */
export function facetOf(source: string): string {
  if (familyOf(source) === 'reference') return source;
  return source.includes('-') ? source.slice(0, source.lastIndexOf('-')) : BARE_FACET;
}

/** The families present in a slot list, in `FAMILY_ORDER`. The wall's slot
 *  route reports only slots that have renders, so a family nobody has drawn
 *  never gets a segment. */
export function familiesIn(sources: readonly { source: string }[]): Family[] {
  const seen = new Set(sources.map((s) => familyOf(s.source)));
  return FAMILY_ORDER.filter((f) => seen.has(f));
}

/** The slot to show after a family change: the same facet if the new family
 *  drew it, else that family's most-populated slot. The route orders by
 *  population, so first-in-family is that one. */
export function slotIn(sources: readonly { source: string }[],
                       family: Family, facet: string): string | null {
  const mine = sources.filter((s) => familyOf(s.source) === family);
  const same = mine.find((s) => facetOf(s.source) === facet);
  return (same ?? mine[0])?.source ?? null;
}
