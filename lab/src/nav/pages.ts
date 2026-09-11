import type { LabPage } from '@weasel-js/labkit';

/** The lab's pages, in the order the switcher lists them. The scratch
 *  previews (`/badges`, `/sticker-candidates`) stay off it: they are compare
 *  sheets you open once from a link, not places to be.
 *  Extensionless: the dev server maps `/corpus` to `corpus.html`. A built
 *  `dist` served without that middleware still answers the `.html` names,
 *  which `currentPage` matches too. */
export const PAGES: LabPage[] = [
  { href: '/corpus', label: 'Wall' },
  { href: '/stats', label: 'Dashboard' },
  { href: '/ingest', label: 'Ingestion' },
];
