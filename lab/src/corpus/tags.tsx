import { BadgeSwatch } from '@lab/corpus/BadgeSwatch';
import { ALL_BADGES } from '@lab/corpus/paint';
import { yearRange } from '@lab/corpus/years';
import '@lab/corpus/tags.css';

export { yearRange };

/** How big a tag badge is set here. Larger than the legend's 14px swatch:
 *  this one carries a word, and the word has to hold its own against the
 *  body copy beside it. */
const TAG_BOX = 17;

/** The tag row both detail views show under the part's name.
 *
 *  A tag the wall badges is drawn as that badge, with the word set on the
 *  badge's own field -- the same artwork the thumbnail wears, so a reader
 *  learns the mark here and recognizes it on the cells. Tags with no badge
 *  keep the plain pill.
 *
 *  `tags` is optional because the lab's server is long-lived and can be
 *  older than the page in front of it -- a missing field must not blank the
 *  view it appears in. */
export function Tags({ tags }: { tags?: string[] }) {
  if (!tags || tags.length === 0) return null;
  return (
    <ul className="corpus-tags">
      {tags.map((tag) => {
        const badge = ALL_BADGES[tag];
        if (!badge) {
          return <li key={tag} className="corpus-tag" data-tag={tag}>{tag}</li>;
        }
        // The badge is aria-hidden, so its word is not in the accessibility
        // tree; the list item carries it as text instead.
        return (
          <li key={tag} className="corpus-tag-badge" data-tag={tag}>
            <BadgeSwatch badge={badge} label={tag} box={TAG_BOX} />
            <span className="corpus-visually-hidden">{tag}</span>
          </li>
        );
      })}
    </ul>
  );
}
