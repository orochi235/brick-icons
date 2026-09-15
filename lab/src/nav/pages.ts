import type { LabPage } from '@weasel-js/labkit';

/** The lab's pages, in the order the switcher lists them. The scratch
 *  previews (`/badges`, `/sticker-candidates`) stay off it: they are compare
 *  sheets you open once from a link, not places to be.
 *  Extensionless: the dev server maps `/corpus` to `corpus.html`. A built
 *  `dist` served without that middleware still answers the `.html` names,
 *  which `currentPage` matches too. */
/** The lab's own entry. Not `/`: labkit strips a trailing slash before
 *  matching, so an entry for the root can never be marked as the page open. */
export const LAB_PATH = '/index';

export const PAGES: LabPage[] = [
  { href: LAB_PATH, label: 'Lab' },
  { href: '/corpus', label: 'Wall' },
  { href: '/wall', label: 'New wall' },
  { href: '/stats', label: 'Dashboard' },
  { href: '/ingest', label: 'Ingestion' },
];
