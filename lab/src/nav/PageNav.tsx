import '@lab/nav/PageNav.css';

export interface Page {
  /** The page's own URL, which is also how the nav knows which one is open. */
  href: string;
  label: string;
}

/** The lab's pages, in the order the nav lists them. The scratch previews
 *  (`badges.html`, `sticker-candidates.html`) stay off it: they are compare
 *  sheets you open once from a link, not places to be. */
export const PAGES: Page[] = [
  { href: '/corpus.html', label: 'Wall' },
  { href: '/stats.html', label: 'Dashboard' },
];

/** Which of `pages` a path is on, or -1. Matched on the filename so a query
 *  string or a trailing slash cannot lose the highlight. */
export function currentIndex(path: string, pages: Page[] = PAGES): number {
  const here = path.split('?')[0]!.split('#')[0]!.replace(/\/$/, '');
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
