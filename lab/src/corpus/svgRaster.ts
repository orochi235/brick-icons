/** Rasterizing a render's SVG at a chosen size -- not the intrinsic one.
 *
 *  The renders declare only a `viewBox`, no `width`/`height`. An `<img>`
 *  holding that SVG decodes at an engine-chosen default size, and
 *  `drawImage` onto a bigger destination rect then stretches that decode --
 *  the same blur as upscaling a small PNG, just one layer removed. Setting
 *  explicit `width`/`height` on the SVG itself (leaving `viewBox` and
 *  `preserveAspectRatio` alone, so the letterboxing bakes did stays intact)
 *  fixes the size the decoder targets before any scaling happens.
 */

const OPEN_SVG_TAG = /<svg\b[^>]*>/;

/** `svgText` with its root tag's `width`/`height` set to `w`/`h`, replacing
 *  either attribute if already present. */
export function injectSize(svgText: string, w: number, h: number): string {
  return svgText.replace(OPEN_SVG_TAG, (tag) => {
    const stripped = tag
      .replace(/\swidth="[^"]*"/, '')
      .replace(/\sheight="[^"]*"/, '');
    return stripped.replace(/^<svg/, `<svg width="${w}" height="${h}"`);
  });
}

/** A decoded SVG, rasterized at exactly `w`x`h` device pixels.
 *
 *  `createImageBitmap` decodes the blob directly, with no DOM `<img>`
 *  natural-size step to get wrong -- but Chrome throws `InvalidStateError`
 *  on any SVG blob, so there it is the `<img>`-into-canvas fallback that
 *  runs, sized the same way for the same reason. */
export async function rasterizeSvg(svgText: string, w: number, h: number):
    Promise<CanvasImageSource> {
  const sized = injectSize(svgText, w, h);
  const blob = new Blob([sized], { type: 'image/svg+xml' });
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(blob, {
        resizeWidth: w, resizeHeight: h, resizeQuality: 'high',
      });
    } catch {
      /* fall through to the <img> path below */
    }
  }
  const url = URL.createObjectURL(blob);
  try {
    const img = new Image(w, h);
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('svg decode failed'));
      img.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('no 2d context to rasterize into');
    ctx.drawImage(img, 0, 0, w, h);
    return canvas;
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** The render at `url`, as text -- held by the caller, because rerastering a
 *  cell the zoom drifted past must not cost another few hundred KB. */
export async function fetchText(url: string): Promise<string> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.text();
}

/** Fetches the render at `url` and rasterizes it at `w`x`h`. */
export async function fetchAndRasterize(url: string, w: number, h: number):
    Promise<CanvasImageSource> {
  return rasterizeSvg(await fetchText(url), w, h);
}
