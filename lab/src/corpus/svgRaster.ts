/** Rasterizing a slot's render at a chosen size -- not the intrinsic one.
 *
 *  The SVG renders declare only a `viewBox`, no `width`/`height`. An `<img>`
 *  holding that SVG decodes at an engine-chosen default size, and
 *  `drawImage` onto a bigger destination rect then stretches that decode --
 *  the same blur as upscaling a small PNG, just one layer removed. Setting
 *  explicit `width`/`height` on the SVG itself (leaving `viewBox` and
 *  `preserveAspectRatio` alone, so the letterboxing bakes did stays intact)
 *  fixes the size the decoder targets before any scaling happens.
 *
 *  A slot need not hold SVG at all -- `ldview` is WebP -- so a render travels
 *  as bytes, and is sized only where sizing means anything.
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

/** `blob` with a `w`x`h` sized SVG root, or `blob` itself. A raster carries
 *  its own dimensions already, and reading one as text destroys it. */
export async function sizedBlob(blob: Blob, w: number, h: number):
    Promise<Blob> {
  if (blob.type !== 'image/svg+xml') return blob;
  return new Blob([injectSize(await blob.text(), w, h)], { type: blob.type });
}

/** A decoded render, rasterized at exactly `w`x`h` device pixels.
 *
 *  `createImageBitmap` decodes the blob directly, with no DOM `<img>`
 *  natural-size step to get wrong -- but Chrome throws `InvalidStateError`
 *  on any SVG blob, so there it is the `<img>`-into-canvas fallback that
 *  runs, sized the same way for the same reason. */
export async function rasterize(render: Blob, w: number, h: number):
    Promise<CanvasImageSource> {
  const blob = await sizedBlob(render, w, h);
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
      img.onerror = () => reject(new Error('render decode failed'));
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

/** The render at `url`, as bytes -- held by the caller, because rerastering a
 *  cell the zoom drifted past must not cost another few hundred KB. Bytes and
 *  not text: reading a WebP slot as UTF-8 corrupts it past decoding, which is
 *  what left `ldview` on its 128px bake at the vector rung. */
export async function fetchRender(url: string): Promise<Blob> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.blob();
}

/** Fetches the render at `url` and rasterizes it at `w`x`h`. */
export async function fetchAndRasterize(url: string, w: number, h: number):
    Promise<CanvasImageSource> {
  return rasterize(await fetchRender(url), w, h);
}
