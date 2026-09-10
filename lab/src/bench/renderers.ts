/** The two executors under test, behind one interface.
 *
 *  Both take the identical `PaintCommand[]` and paint into their own canvas of
 *  the same size. Nothing here decides what to draw -- `paintCommands` already
 *  did -- so the difference between them is the drawing, which is the whole
 *  point of the measurement.
 */
import { createScene, renderSceneToCanvas, type View } from '@weasel-js/core';
import { drawPaintCommand } from '@lab/corpus/draw2d';
import { scenePainter, type Sheets } from '@lab/corpus/drawScene';
import type { PaintCommand } from '@lab/corpus/paint';
import type { Palette } from '@lab/corpus/palette';
import { toDrawCommands, type Sampling } from '@lab/corpus/toDrawCommands';

export interface Frame { width: number; height: number; dpr: number }

export interface WallRenderer {
  readonly name: string;
  /** Every canvas this executor paints into, bottom first. Read back by the
   *  harness to check it actually drew -- a stack is flattened in this order,
   *  so an overlay layer that stopped drawing shows up as drift. */
  readonly layers: readonly HTMLCanvasElement[];
  /** Features of the last painted list this executor does not reproduce. */
  readonly unsupported: ReadonlySet<string>;
  paint(cmds: readonly PaintCommand[], frame: Frame): void;
}

/** `paintCommands` emits screen-space coordinates, so the scene renderer must
 *  not apply a camera on top of them. */
const IDENTITY: View = { x: 0, y: 0, scale: { x: 1, y: 1 } };

function size(canvas: HTMLCanvasElement, frame: Frame) {
  const w = Math.round(frame.width * frame.dpr);
  const h = Math.round(frame.height * frame.dpr);
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
  canvas.style.width = `${frame.width}px`;
  canvas.style.height = `${frame.height}px`;
}

export function canvas2dRenderer(canvas: HTMLCanvasElement,
                                 sheet: HTMLImageElement | null,
                                 palette: Palette): WallRenderer {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('no 2d context');
  return {
    name: 'canvas2d',
    layers: [canvas],
    unsupported: new Set<string>(),
    paint(cmds, frame) {
      size(canvas, frame);
      ctx.setTransform(frame.dpr, 0, 0, frame.dpr, 0, 0);
      ctx.clearRect(0, 0, frame.width, frame.height);
      ctx.imageSmoothingEnabled = true;
      for (const cmd of cmds) drawPaintCommand(ctx, cmd, sheet, palette);
    },
  };
}

/** Weasel's WebGL2 renderer, reached with no scene nodes at all.
 *
 *  A node per cell is what makes a scene graph lose at this scale -- it is why
 *  windease was ruled out for the wall -- so the whole list rides in as
 *  `extraCommands` over an empty scene. */
export function sceneRenderer(canvas: HTMLCanvasElement,
                              sheet: ImageBitmap | null,
                              sampling: Sampling = 'nearest'): WallRenderer {
  const scene = createScene<unknown, 'main'>({ systemLayers: [{ id: 'main' }] });
  let unsupported: ReadonlySet<string> = new Set();
  return {
    name: `scene/${sampling}`,
    layers: [canvas],
    get unsupported() { return unsupported; },
    paint(cmds, frame) {
      const mapped = toDrawCommands(cmds, sheet, sampling);
      unsupported = mapped.unsupported;
      renderSceneToCanvas({
        canvas,
        scene,
        view: IDENTITY,
        width: frame.width,
        height: frame.height,
        dpr: frame.dpr,
        drawOne: () => [],
        extraCommands: mapped.commands,
      });
    },
  };
}

/** The wall's own hybrid: weasel draws the cell bodies, canvas2d draws the
 *  overlays on a layer above.
 *
 *  This is `scenePainter` itself rather than a bench-side copy of it, so the
 *  number belongs to the code the `sceneRenderer` param turns on. It is the
 *  only executor here that draws a rung wearing badges -- the bare scene
 *  renderer withholds those -- which is what the second layer costs and buys.
 */
export function hybridRenderer(gl: HTMLCanvasElement,
                               overlay: HTMLCanvasElement,
                               sheets: Sheets,
                               palette: Palette,
                               sampling: Sampling = 'linear'): WallRenderer {
  const painter = scenePainter(gl, overlay);
  return {
    name: `hybrid/${sampling}`,
    layers: [gl, overlay],
    // What NEITHER half drew. The residue pass covers every name the mapping
    // declines, so this is empty unless one is added to the mapping alone.
    get unsupported() { return painter.unpainted; },
    paint(cmds, frame) { painter.paint(cmds, frame, sheets, palette, sampling); },
  };
}
