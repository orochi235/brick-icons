import { useEffect, useState } from 'react';

/** The part of the page a pinch has actually left on screen.
 *
 *  Chrome's pinch zoom magnifies the composited layer and touches nothing the
 *  page can normally see: `devicePixelRatio` does not move, CSS pixels do not
 *  move, and neither does `innerWidth`. Measured at a page scale of 3, dpr
 *  stays 1 and innerWidth stays 1280 while `visualViewport.scale` reads 3 and
 *  `visualViewport.width` reads 427. So a canvas keeps drawing at its
 *  unpinched resolution and the compositor blows it up -- which is why the
 *  wall's thumbnails go soft under a pinch and its mip level never moves.
 *
 *  `left`/`top`/`width`/`height` are client CSS pixels: the window-relative
 *  rectangle still visible. `scale` is the magnification.
 */
export interface VisualViewport2 {
  scale: number;
  left: number;
  top: number;
  width: number;
  height: number;
}

function read(): VisualViewport2 {
  const vv = typeof window !== 'undefined' ? window.visualViewport : undefined;
  if (!vv) {
    const w = typeof window !== 'undefined' ? window.innerWidth : 0;
    const h = typeof window !== 'undefined' ? window.innerHeight : 0;
    return { scale: 1, left: 0, top: 0, width: w, height: h };
  }
  return { scale: vv.scale, left: vv.offsetLeft, top: vv.offsetTop,
           width: vv.width, height: vv.height };
}

function same(a: VisualViewport2, b: VisualViewport2): boolean {
  return a.scale === b.scale && a.left === b.left && a.top === b.top
      && a.width === b.width && a.height === b.height;
}

export function useVisualViewport(): VisualViewport2 {
  const [state, setState] = useState<VisualViewport2>(read);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let frame = 0;
    // Coalesced to a frame: a pinch fires resize and scroll continuously, and
    // every one of them would otherwise resize the canvas backing store.
    const sync = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        setState((current) => {
          const next = read();
          return same(current, next) ? current : next;
        });
      });
    };
    vv.addEventListener('resize', sync);
    vv.addEventListener('scroll', sync);
    sync();
    return () => {
      if (frame) cancelAnimationFrame(frame);
      vv.removeEventListener('resize', sync);
      vv.removeEventListener('scroll', sync);
    };
  }, []);

  return state;
}
