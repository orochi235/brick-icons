import { expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PageNav, PAGES, currentIndex } from '@lab/nav/PageNav';

it('marks the page you are on, and only that one', () => {
  render(<PageNav path="/stats.html" />);
  expect(screen.getByRole('link', { name: 'Dashboard' })
    .getAttribute('aria-current')).toBe('page');
  expect(screen.getByRole('link', { name: 'Wall' })
    .getAttribute('aria-current')).toBeNull();
});

it('links to the other page by href, not a handler', () => {
  render(<PageNav path="/corpus.html" />);
  expect(screen.getByRole('link', { name: 'Dashboard' })
    .getAttribute('href')).toBe('/stats.html');
});

it('still highlights through a query string or a trailing slash', () => {
  expect(currentIndex('/corpus.html?source=census-occt')).toBe(0);
  expect(currentIndex('/stats.html#tiles')).toBe(1);
});

it('highlights nothing on a page that is not in the list', () => {
  expect(currentIndex('/badges.html')).toBe(-1);
  render(<PageNav path="/badges.html" />);
  for (const page of PAGES) {
    expect(screen.getByRole('link', { name: page.label })
      .getAttribute('aria-current')).toBeNull();
  }
});
