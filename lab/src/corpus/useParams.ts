import { useCallback, useEffect, useState } from 'react';
import { COLOR_PARAM_KEYS, DEFAULT_PARAMS, type Params } from '@lab/corpus/params';
import { PARAM_CSS_VAR } from '@lab/corpus/palette';

const STORAGE_KEY = 'brick-icons-lab.corpus-params';

function loadStored(): Params {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PARAMS;
    return { ...DEFAULT_PARAMS, ...(JSON.parse(raw) as Partial<Params>) };
  } catch {
    return DEFAULT_PARAMS;
  }
}

function persist(params: Params): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(params));
  } catch {
    // A full or disabled store is not worth failing the wall over.
  }
}

/** `.lk-root` carries the CSS custom properties `readPalette` resolves --
 *  it is `LabShell`'s own wrapper, not `document.documentElement`, so a
 *  write has to land there or `.lk-root`'s own declared value would win. */
function writeColorVars(params: Params): void {
  const root = document.querySelector<HTMLElement>('.lk-root');
  if (!root) return;
  for (const key of COLOR_PARAM_KEYS) root.style.setProperty(PARAM_CSS_VAR[key], params[key]);
}

export interface UseParamsResult {
  params: Params;
  setParam: <K extends keyof Params>(key: K, value: Params[K]) => void;
  reset: () => void;
}

/**
 * The wall's tuning constants: persisted to `localStorage`, resettable to
 * their tuned defaults.
 *
 * A color param also writes its CSS custom property onto `.lk-root` --
 * `readPalette` and `Wall`'s own mutation observer are what turn that into a
 * repaint. Everything else reaches the wall as an ordinary prop; wiring
 * color through React state as well would fork that pipeline.
 */
export function useParams(): UseParamsResult {
  const [params, setParams] = useState<Params>(loadStored);

  useEffect(() => {
    writeColorVars(params);
    persist(params);
  }, [params]);

  const setParam = useCallback(<K extends keyof Params>(key: K, value: Params[K]) => {
    setParams((prev) => ({ ...prev, [key]: value }));
  }, []);

  const reset = useCallback(() => setParams(DEFAULT_PARAMS), []);

  return { params, setParam, reset };
}
