// jsdom implements neither, and both are load-bearing: the mark layer captures
// the pointer for a drag, and a pane reports its body size to place marks.
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
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
