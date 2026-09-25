import { useEffect, useRef } from 'react';
import { applyFilter, type ImageFilter } from '@pezlie/wall/src/filter';

/** An `<img>` drawn through `filter`, for a thumbnail outside the wall's
 *  canvas that has to match what the wall draws. */
export function FilteredImage({ src, alt, filter, className }: {
  src: string; alt: string; filter: ImageFilter; className?: string;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let live = true;
    const img = new Image();
    img.onload = () => {
      const canvas = ref.current;
      if (!live || !canvas) return;
      const out = applyFilter(img, filter);
      canvas.width = out.width;
      canvas.height = out.height;
      canvas.getContext('2d')?.drawImage(out, 0, 0);
    };
    img.src = src;
    return () => { live = false; };
  }, [src, filter]);
  return <canvas ref={ref} className={className} role="img" aria-label={alt} />;
}
