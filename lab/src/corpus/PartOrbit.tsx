import { useEffect, useRef, useState } from 'react';
import { HOME } from '@lab/panes/camera';
import { ThreePane } from '@lab/panes/ThreePane';
import type { Box, ThreeStyle } from '@lab/panes/viewport';
import '@lab/corpus/PartOrbit.css';

/** No render to register against, so the part frames itself by its own size.
 *  The lightbox's renders are each drawn at their own slot's config and this
 *  view belongs to none of them -- it is the part, not a slot's picture of it. */
const STYLE: ThreeStyle = { opacity: 1, lineWidth: 2, background: null };

/** The part in 3D, turned by dragging, inside the lightbox.
 *
 *  Default-exported as well as named: the lightbox reaches it through
 *  `React.lazy`, so three.js and the loader stay out of the wall's bundle
 *  until somebody asks to turn a part around.
 */
export function PartOrbit({ part, angle = '30,45' }:
                          { part: string; angle?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box>({ width: 0, height: 0 });
  const [pose, setPose] = useState(angle);

  // The frustum needs a measured box, and the panel is revealed by a toggle
  // rather than laid out with the page -- so its size arrives after mount.
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const r = entry!.contentRect;
      setBox({ width: r.width, height: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="corpus-orbit" ref={host}>
      <ThreePane part={part} angle={pose} fit={null} box={box} view={HOME}
                 style={STYLE} orbit="own" onSettle={setPose} />
      <span className="corpus-orbit-pose">{pose}</span>
    </div>
  );
}

export default PartOrbit;
