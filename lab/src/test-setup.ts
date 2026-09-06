// jsdom implements neither, and both are load-bearing: the mark layer captures
// the pointer for a drag, and a pane reports its body size to place marks.
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

// Node's own experimental Web Storage global shadows jsdom's, but stays
// inert without `--localstorage-file` -- `localStorage` reads as `undefined`
// rather than a working `Storage`, whichever provider set it up. Give it an
// in-memory one so a test doesn't need a CLI flag to persist anything.
if (typeof globalThis.localStorage === 'undefined') {
  class MemoryStorage implements Storage {
    #store = new Map<string, string>();
    get length() { return this.#store.size; }
    clear() { this.#store.clear(); }
    getItem(key: string) { return this.#store.has(key) ? this.#store.get(key)! : null; }
    key(index: number) { return [...this.#store.keys()][index] ?? null; }
    removeItem(key: string) { this.#store.delete(key); }
    setItem(key: string, value: string) { this.#store.set(key, String(value)); }
  }
  const storage = new MemoryStorage();
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true });
  Object.defineProperty(globalThis.window, 'localStorage', { value: storage, configurable: true });
}

if (!('ResizeObserver' in globalThis)) {
  (globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// jsdom has no PointerEvent, so testing-library falls back to a bare `Event`
// and every coordinate arrives undefined -- a drag then reports a NaN mark
// rather than failing. MouseEvent carries the coordinates the layer reads.
if (!('PointerEvent' in globalThis)) {
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number;

    constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  }
  (globalThis as { PointerEvent?: unknown }).PointerEvent = PointerEventPolyfill;
  (globalThis.window as unknown as { PointerEvent?: unknown }).PointerEvent =
    PointerEventPolyfill;
}
