import { yearRange } from '@lab/corpus/years';
import '@lab/corpus/tags.css';

export { yearRange };

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
