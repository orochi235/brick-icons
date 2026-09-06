import '@lab/corpus/tags.css';

/** How a part's years read on a detail view: `1979–2026`, `1979` for a part
 *  that came and went in one year, and nothing at all for a part the
 *  catalogs do not list. */
export function yearRange(from: number | null, to: number | null): string | null {
  if (from == null && to == null) return null;
  if (from == null || to == null) return String(from ?? to);
  return from === to ? String(from) : `${from}–${to}`;
}

/** The tag row both detail views show under the part's name.
 *
 *  `tags` is optional because the lab's server is long-lived and can be
 *  older than the page in front of it -- a missing field must not blank the
 *  view it appears in. */
export function Tags({ tags }: { tags?: string[] }) {
  if (!tags || tags.length === 0) return null;
  return (
    <ul className="corpus-tags">
      {tags.map((tag) => (
        <li key={tag} className="corpus-tag" data-tag={tag}>{tag}</li>
      ))}
    </ul>
  );
}
