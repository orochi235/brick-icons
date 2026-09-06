/** Filing a defect from the wall, in the vocabulary the defect list already
 *  uses: `tests/goldens/defects.toml` ids read `<part>-<what is wrong>`, and
 *  `engines` names an engine, never a slot. */

/** The engine behind a slot name. A facet puts its own name in the middle --
 *  `census-white-naive` is naive drawing the white facet -- so the engine is
 *  the last segment. Mirrors `cells.engine_for`. */
export function engineFor(source: string): string {
  return source.startsWith('census-') ? source.slice(source.lastIndexOf('-') + 1) : source;
}

/** A hand-written-looking id for a filed defect: the part, then the title cut
 *  to a few words. The server rejects a duplicate rather than overwriting, and
 *  the message says so. */
export function defectId(part: string, title: string): string {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '').split('-').filter(Boolean).slice(0, 5).join('-');
  return slug ? `${part}-${slug}` : part;
}
