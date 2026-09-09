/** `/bench` -- the wall's paint loop against weasel's scene renderer.
 *
 *  Everything on this page exists to make one number trustworthy, so it draws
 *  the real corpus at the real cell sizes and reports each rung as it lands
 *  rather than at the end.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { createClient } from '@lab/api/client';
import { gridLayout } from '@lab/corpus/layout';
import { DEFAULT_APPEARANCE, paintCommands } from '@lab/corpus/paint';
import { DEFAULT_PALETTE } from '@lab/corpus/palette';
import { SHEET_LEVELS } from '@lab/corpus/useSheets';
import { levelFor } from '@lab/corpus/levels';
import type { Cell, SheetManifest } from '@lab/corpus/types';
import { visibleRange } from '@lab/corpus/visible';
import { canvas2dRenderer, sceneRenderer } from '@lab/bench/renderers';
import { runBench, type Rung, type RungResult } from '@lab/bench/harness';

interface SheetSet { manifest: SheetManifest; img: HTMLImageElement; bitmap: ImageBitmap }
interface BenchRung extends Rung { sheet: SheetSet }
import '@lab/bench/bench.css';

const SOURCE = 'reference';
const GAP = 4;
const WIDTH = 1200;
const HEIGHT = 900;

/** Sizes that stay inside a baked rung. Past level 32 a cell wants the loose
 *  PNG or its vector, which is a different question from this one. */
const CELL_SIZES = [8, 12, 16, 24, 32, 48, 56];

function gpu(): string {
  const c = document.createElement('canvas');
  const gl = c.getContext('webgl2');
  if (!gl) return 'no WebGL2 context — the scene renderer cannot draw here';
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  return dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : 'WebGL2, renderer undisclosed';
}

export function Bench() {
  const [lines, setLines] = useState<string[]>([]);
  const [results, setResults] = useState<RungResult[] | null>(null);
  const [status, setStatus] = useState('Loading the corpus…');
  const [busy, setBusy] = useState(false);
  /** One entry per baked level. The wall swaps sheets by cell size so a tile
   *  is drawn near 1:1; pinning one sheet across every rung would measure
   *  minification instead of the renderer. */
  const data = useRef<{ cells: Cell[]; levels: Map<number, SheetSet> } | null>(null);
  const twoD = useRef<HTMLCanvasElement>(null);
  const glNearest = useRef<HTMLCanvasElement>(null);
  const glLinear = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const client = createClient();
    let live = true;
    void (async () => {
      const body = await client.cells(SOURCE);
      const levels = new Map<number, SheetSet>();
      for (const level of SHEET_LEVELS) {
        const manifest = await client.sheetManifest(SOURCE, level);
        const img = new Image();
        img.src = `/api/thumbs/${SOURCE}/sheet-${level}.webp`
          + (manifest.version ? `?v=${manifest.version}` : '');
        await img.decode();
        levels.set(level, { manifest, img, bitmap: await createImageBitmap(img) });
      }
      if (!live) return;
      data.current = { cells: body.cells, levels };
      setStatus(`${body.cells.length.toLocaleString()} cells · `
        + `${SHEET_LEVELS.length} baked levels · ${gpu()}`);
    })().catch((e: unknown) => { setStatus(`failed: ${String(e)}`); });
    return () => { live = false; };
  }, []);

  const run = useCallback(() => {
    const d = data.current;
    const a = twoD.current;
    const b = glNearest.current;
    const c = glLinear.current;
    if (!d || !a || !b || !c) return;
    setBusy(true);
    setLines([]);
    setResults(null);

    const rungs: BenchRung[] = CELL_SIZES.map((cellPx) => {
      const cols = Math.max(1, Math.floor((WIDTH + GAP) / (cellPx + GAP)));
      const { rects } = gridLayout(d.cells, { cell: cellPx, gap: GAP, cols });
      const cam = { x: 0, y: 0, scale: { x: 1, y: 1 } };
      const visible = visibleRange(rects, cam, { width: WIDTH, height: HEIGHT });
      const level = d.levels.get(levelFor(cellPx))!;
      return {
        cellPx,
        level: levelFor(cellPx),
        sheet: level,
        commands: paintCommands({
          cells: d.cells, rects, visible, cam, manifest: level.manifest,
          palette: DEFAULT_PALETTE, appearance: DEFAULT_APPEARANCE,
          tint: 'status',
        }),
      };
    });

    // Yielded to the browser so the first rung's line paints before the run
    // takes the main thread for the rest of it.
    requestAnimationFrame(() => {
      const out = runBench({
        rungs,
        renderersFor: (rung) => [
          canvas2dRenderer(a, rung.sheet.img, DEFAULT_PALETTE),
          sceneRenderer(b, rung.sheet.bitmap, DEFAULT_PALETTE, 'nearest'),
          sceneRenderer(c, rung.sheet.bitmap, DEFAULT_PALETTE, 'linear'),
        ],
        frame: { width: WIDTH, height: HEIGHT, dpr: window.devicePixelRatio || 1 },
        onLine: (line) => { setLines((prev) => [...prev, line]); },
      });
      setResults(out);
      setBusy(false);
    });
  }, []);

  return (
    <main className="bench">
      <h1>Wall paint: canvas2d against weasel&apos;s scene</h1>
      <p className="bench__status">{status}</p>
      <p className="bench__note">
        Level {SHEET_LEVELS[1]} sheet, {WIDTH}×{HEIGHT} viewport, identical command
        list to both. A rung is only given a ratio when both renderers drew the
        same pixels.
      </p>
      <button type="button" onClick={run} disabled={busy || !data.current}>
        {busy ? 'Running…' : 'Run'}
      </button>

      {lines.length > 0 && (
        <pre className="bench__log">{lines.join('\n')}</pre>
      )}

      {results && (
        <table className="bench__table">
          <thead>
            <tr>
              <th>cell</th><th>level</th><th>commands</th>
              {results[0]!.timings.map((t) => <th key={t.name}>{t.name}</th>)}
              <th>note</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.cellPx}>
                <td>{r.cellPx}px</td>
                <td>{r.level}</td>
                <td>{r.commands.toLocaleString()}</td>
                {r.timings.map((t, i) => (
                  <td key={t.name}>
                    {t.median.toFixed(1)}ms
                    {i > 0 && !r.incomparable
                      && ` (${(r.timings[0]!.median / t.median).toFixed(2)}×)`}
                  </td>
                ))}
                <td className="bench__withheld">{r.incomparable}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="bench__canvases">
        <figure><figcaption>canvas2d</figcaption><canvas ref={twoD} /></figure>
        <figure><figcaption>scene/nearest</figcaption><canvas ref={glNearest} /></figure>
        <figure><figcaption>scene/linear</figcaption><canvas ref={glLinear} /></figure>
      </div>
    </main>
  );
}
