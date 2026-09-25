import { useEffect, useRef } from 'react';
import { applyFilter, type ImageFilter } from '@pezlie/wall/src/filter';

function load(src: string): Promise<HTMLImageElement | null> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

/** An `<img>` drawn through `filter`, for a thumbnail outside the wall's
 *  canvas that has to match what the wall draws. `maskSrc` is the image's
 *  mask where it may have one; a missing mask filters without. */
export function FilteredImage({ src, maskSrc, alt, filter, className }: {
  src: string; maskSrc?: string; alt: string; filter: ImageFilter; className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let live = true;
    void Promise.all([load(src), maskSrc ? load(maskSrc) : null]).then(([img, mask]) => {
      const canvas = ref.current;
      if (!live || !canvas || !img) return;
      const out = applyFilter(img, filter, mask);
      canvas.width = out.width;
      canvas.height = out.height;
      canvas.getContext('2d')?.drawImage(out, 0, 0);
    });
    return () => { live = false; };
  }, [src, maskSrc, filter]);
  return <canvas ref={ref} className={className} role="img" aria-label={alt} />;
}
