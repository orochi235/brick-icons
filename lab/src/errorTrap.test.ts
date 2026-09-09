import { beforeEach, afterEach, expect, test, vi } from 'vitest';
/** Loaded as source and run, not imported: it ships as a classic script in
 *  `public/` precisely so it survives the module graph failing. */
import SRC from '../public/error-trap.js?raw';

const DEADLINE = 5000;

function boot() {
  new Function(SRC)();
}

function trap() {
  return document.getElementById('lab-trap');
}

beforeEach(() => {
  vi.useFakeTimers();
  // jsdom's getContext throws "Not implemented" through the virtual console.
  // The trap catches it and reports it, which is right in a browser and only
  // noise here.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
  document.head.innerHTML = '';
  document.body.innerHTML = '<div id="root"></div>';
});

afterEach(() => {
  vi.useRealTimers();
});

test('says so when nothing ever renders', () => {
  boot();
  expect(trap()).toBeNull();
  vi.advanceTimersByTime(DEADLINE);
  expect(trap()?.textContent).toContain('The page did not start');
});

test('stays out of the way when the page mounted', () => {
  boot();
  document.getElementById('root')!.appendChild(document.createElement('div'));
  vi.advanceTimersByTime(DEADLINE);
  expect(trap()).toBeNull();
});

test('reports an error raised after a successful mount, as a badge', () => {
  boot();
  document.getElementById('root')!.appendChild(document.createElement('div'));
  vi.advanceTimersByTime(DEADLINE);

  window.dispatchEvent(new ErrorEvent('error', { message: 'kaboom' }));
  expect(trap()?.textContent).toContain('kaboom');
  expect(trap()?.className).toContain('lab-trap--badge');
});

test('ignores the ResizeObserver loop notice, which fires on every load', () => {
  boot();
  document.getElementById('root')!.appendChild(document.createElement('div'));
  vi.advanceTimersByTime(DEADLINE);

  window.dispatchEvent(new ErrorEvent('error', {
    message: 'ResizeObserver loop completed with undelivered notifications.',
  }));
  expect(trap()).toBeNull();
});

test('names the resource when a script or image fails to load', () => {
  boot();
  const img = document.createElement('img');
  img.src = 'http://example.test/sheet-32.webp';
  document.body.appendChild(img);
  img.dispatchEvent(new Event('error', { bubbles: false }));

  vi.advanceTimersByTime(DEADLINE);
  const text = trap()?.textContent ?? '';
  expect(text).toContain('img failed to load');
  expect(text).toContain('sheet-32.webp');
});

test('a page with no #root at all still reports', () => {
  document.body.innerHTML = '';
  boot();
  vi.advanceTimersByTime(DEADLINE);
  expect(trap()?.textContent).toContain('The page did not start');
});
