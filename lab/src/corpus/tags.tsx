import '@lab/corpus/tags.css';

/** How a part's years read on a detail view: `1979–` while it is still being
 *  made, `1958–1978` once it is not, `1967` for a part that came and went in
 *  one year, and nothing at all for a part the catalogs do not list.
 *
 *  A part still in production has no end year to show -- its last set is
 *  simply the newest one so far, and printing that reads as the year it
 *  stopped. `retired` is the server's call (`brick_icons/tags.py`), not a
 *  comparison made here. */
export function yearRange(from: number | null, to: number | null,
                          retired: boolean): string | null {
  if (from == null && to == null) return null;
  if (from == null) return retired ? `–${to}` : null;
  if (!retired) return `${from}–`;
  if (to == null) return String(from);
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
