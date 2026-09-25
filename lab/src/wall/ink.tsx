import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'brick-icons.wall.ink';
/** Every change refilters the sheets, and a 5652px atlas is not free; a drag
 *  across the picker commits when it pauses rather than on every step. */
const COMMIT_MS = 150;
const DEFAULT_PICK = '#1f5fbf';

function stored(): string | null {
  try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
}

function store(ink: string | null) {
  try {
    if (ink) localStorage.setItem(STORAGE_KEY, ink);
    else localStorage.removeItem(STORAGE_KEY);
  } catch { /* a remembered ink is a convenience */ }
}

/** The color the wall's drawings are inked in, or null for as rendered. */
export function useInk(): [string | null, (ink: string | null) => void] {
  const [ink, setInk] = useState<string | null>(stored);
  const set = useCallback((next: string | null) => { store(next); setInk(next); }, []);
  return [ink, set];
}

function channels(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

/** The picker in the wall's header, and the SVG filter that inks the card's
 *  `<img>` thumbnail the same way pezlie's `inkFilter` inks the canvas. */
export function InkPicker({ ink, onInk }: { ink: string | null;
                                            onInk: (ink: string | null) => void }) {
  const [picked, setPicked] = useState(ink ?? DEFAULT_PICK);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => { if (ink) setPicked(ink); }, [ink]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const pick = (value: string) => {
    setPicked(value);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onInk(value), COMMIT_MS);
  };
  const clear = () => {
    if (timer.current) clearTimeout(timer.current);
    onInk(null);
  };

  const [r, g, b] = channels(ink ?? DEFAULT_PICK);
  return (
    <span className={ink ? 'brick-wall-ink brick-wall-ink--on' : 'brick-wall-ink'}>
      <input type="color" aria-label="ink color" title="ink the drawings in one color"
             value={picked} onChange={(e) => pick(e.target.value)} />
      {ink && (
        <button type="button" className="brick-wall-ink__clear" onClick={clear}
                aria-label="draw as rendered" title="draw as rendered">×</button>
      )}
      {/* Screen with the ink, per channel: v -> ink + (1 - ink) * v. In sRGB,
          as the canvas blends, not the linearRGB a filter defaults to. */}
      <svg className="brick-wall-ink__defs" aria-hidden="true" focusable="false">
        <filter id="brick-wall-ink" colorInterpolationFilters="sRGB">
          <feComponentTransfer>
            <feFuncR type="linear" slope={1 - r} intercept={r} />
            <feFuncG type="linear" slope={1 - g} intercept={g} />
            <feFuncB type="linear" slope={1 - b} intercept={b} />
          </feComponentTransfer>
        </filter>
      </svg>
    </span>
  );
}
