import '@lab/nav/PageNav.css';

export interface Page {
  /** The page's own URL, which is also how the nav knows which one is open. */
  href: string;
  label: string;
}

/** The lab's pages, in the order the nav lists them. The scratch previews
 *  (`/badges`, `/sticker-candidates`) stay off it: they are compare sheets
 *  you open once from a link, not places to be.
 *  Extensionless: the dev server maps `/corpus` to `corpus.html`. A built
 *  `dist` served without that middleware still answers the `.html` names,
 *  which `currentIndex` matches too. */
export const PAGES: Page[] = [
  { href: '/corpus', label: 'Wall' },
  { href: '/stats', label: 'Dashboard' },
  { href: '/ingest', label: 'Ingestion' },
];

/** Which of `pages` a path is on, or -1. Matched on the filename so a query
 *  string, a trailing slash or a leftover `.html` cannot lose the
 *  highlight -- a bookmark from before the URLs lost their extension still
 *  lights the right tab. */
export function currentIndex(path: string, pages: Page[] = PAGES): number {
  const here = path.split('?')[0]!.split('#')[0]!.replace(/\/$/, '').replace(/\.html$/, '');
  return pages.findIndex((p) => here.endsWith(p.href));
}

/** Links between the wall and the dashboard. Anchors rather than buttons:
 *  these are separate documents, so a real href gets middle-click, cmd-click
 *  and the back button without writing any of them. */
export function PageNav({ path = window.location.pathname, pages = PAGES }:
                        { path?: string; pages?: Page[] } = {}) {
  const at = currentIndex(path, pages);
  return (
    <nav className="lab-nav" aria-label="Pages">
      {pages.map((page, i) => (
        <a key={page.href} href={page.href} className="lab-nav-link"
           aria-current={i === at ? 'page' : undefined}>
          {page.label}
        </a>
      ))}
    </nav>
  );
}
