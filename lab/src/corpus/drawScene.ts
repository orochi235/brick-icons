/** The wall's hybrid executor: weasel draws the cell bodies, canvas2d draws
 *  what weasel cannot.
 *
 *  `toDrawCommands` names the features it does not reproduce, and every one of
 *  them is text, a composite, or a measurement -- badges and their punched
 *  marks, the kind strip, captions, the category glyph, the sticker mark, the
 *  caret, band labels, and the loose/vector rung's own images. Those stay on a
 *  transparent 2D canvas stacked over the GL one, which is also where the
 *  `Path2D` cache and the measured typography already live.
 *
 *  The split costs nothing where the win is: `BADGE_MIN_PX` is 56, so below
 *  that a cell wears no overlay at all and the 2D layer draws an empty frame.
 */
import { createScene, renderSceneToCanvas, type View } from '@weasel-js/core';
import {
  CIRCLE_SCALE, GLYPH_SCALE, drawOverlays, drawPaintCommand, drawSticker,
  strokeCaret, strokeSlash,
} from '@lab/corpus/draw2d';
import { THUMB_FACE, WEIGHT_ID } from '@lab/corpus/badges';
import type { PaintCommand } from '@lab/corpus/paint';
import type { Palette } from '@lab/corpus/palette';
import { UNSUPPORTED, toDrawCommands, type Sampling } from '@lab/corpus/toDrawCommands';

export interface Frame { width: number; height: number; dpr: number }

/** `paintCommands` emits screen space, so the scene must not apply a camera
 *  on top of it. */
const IDENTITY: View = { x: 0, y: 0, scale: { x: 1, y: 1 } };

/** Everything `toDrawCommands` left for canvas2d, for one command.
 *
 *  Mirrors `drawPaintCommand` branch for branch, minus the body each branch
 *  draws -- so the two together paint each command exactly once. The offset is
 *  the loupe's, which redraws the same list recentred.
 */
export function drawResidue(ctx: CanvasRenderingContext2D, cmd: PaintCommand,
                            sheet: HTMLImageElement | null, palette: Palette,
                            offset: { x: number; y: number } = { x: 0, y: 0 }) {
  const dx = cmd.dx + offset.x;
  const dy = cmd.dy + offset.y;

  if (cmd.kind === 'sprite') {
    const box = { dx, dy, dw: cmd.dw, dh: cmd.dh };
    // Under the cell's own alpha, the way draw2d draws them inside its group:
    // a dimmed cell's badges dim with it.
    ctx.save();
    ctx.globalAlpha = cmd.alpha ?? 1;
    drawOverlays(ctx, cmd, box);
    ctx.restore();
    if (cmd.caret) strokeCaret(ctx, box, palette);
  } else if (cmd.kind === 'image') {
    // The loose and vector rungs are the cell's own bitmap or SVG, which never
    // reached the mapping: this branch is the whole command.
    drawPaintCommand(ctx, cmd, sheet, palette, offset);
  } else if (cmd.kind === 'fill') {
    const box = { dx, dy, dw: cmd.dw, dh: cmd.dh };
    if (cmd.mark === 'sticker') {
      ctx.save();
      ctx.fillStyle = cmd.fill;
      drawSticker(ctx, dx + cmd.dw / 2, dy + cmd.dh / 2, cmd.dw * CIRCLE_SCALE / 2);
      ctx.restore();
    } else if (cmd.glyph) {
      ctx.save();
      ctx.fillStyle = cmd.fill;
      ctx.font = `${WEIGHT_ID} ${cmd.dh * GLYPH_SCALE}px ${THUMB_FACE}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(cmd.glyph, dx + cmd.dw / 2, dy + cmd.dh / 2 + cmd.dh * 0.03);
      ctx.restore();
    }
    // The border rect is weasel's; only the diagonal is left, and re-stroking
    // the rect over the one already drawn would harden that edge.
    if (cmd.slash) strokeSlash(ctx, { ...box, border: cmd.border, borderWidth: cmd.borderWidth });
    drawOverlays(ctx, cmd, box);
    if (cmd.caret) strokeCaret(ctx, box, palette);
  } else if (cmd.kind === 'label') {
    drawPaintCommand(ctx, cmd, sheet, palette, offset);
  }
}

export interface Sheets {
  /** For weasel: the atlas as a texture source. */
  bitmap: ImageBitmap | null;
  /** For the 2D half: the same atlas, which `drawPaintCommand` blits from on
   *  the loose and vector rungs. */
  img: HTMLImageElement | null;
}

export interface SceneWallPainter {
  /** The features neither half drew. Empty is the invariant -- a name here is
   *  a cell the wall is not painting at all. */
  readonly unpainted: ReadonlySet<string>;
  paint(cmds: readonly PaintCommand[], frame: Frame, sheets: Sheets,
        palette: Palette, sampling?: Sampling): void;
}

/** Which of `UNSUPPORTED`'s features `drawResidue` draws.
 *
 *  Typed against the mapping's own keys, so adding a feature there and not
 *  here fails the build rather than silently going undrawn on the wall. */
const RESIDUE_DRAWS: Record<keyof typeof UNSUPPORTED, boolean> = {
  badges: true,
  strip: true,
  captions: true,
  caret: true,
  sticker: true,
  glyph: true,
  slash: true,
  image: true,
  label: true,
};

const RESIDUE_COVERS: ReadonlySet<string> = new Set(
  (Object.keys(RESIDUE_DRAWS) as (keyof typeof UNSUPPORTED)[])
    .filter((k) => RESIDUE_DRAWS[k]).map((k) => UNSUPPORTED[k]));

/** Paints a `PaintCommand[]` across two stacked canvases.
 *
 *  `gl` carries the bodies and `overlay` sits over it, transparent, carrying
 *  the rest. The scene is the only thing held between paints; the sheets and
 *  the palette come in per paint, so a theme change or a slot swap needs no
 *  new painter and no new GL context.
 */
export function scenePainter(gl: HTMLCanvasElement,
                             overlay: HTMLCanvasElement): SceneWallPainter {
  const scene = createScene<unknown, 'main'>({ systemLayers: [{ id: 'main' }] });
  const ctx = overlay.getContext('2d');
  if (!ctx) throw new Error('no 2d context for the overlay layer');
  let unpainted: ReadonlySet<string> = new Set();

  return {
    get unpainted() { return unpainted; },
    paint(cmds, frame, sheets, palette, sampling = 'nearest') {
      const mapped = toDrawCommands(cmds, sheets.bitmap, sampling);
      unpainted = new Set([...mapped.unsupported].filter((f) => !RESIDUE_COVERS.has(f)));

      renderSceneToCanvas({
        canvas: gl,
        scene,
        view: IDENTITY,
        width: frame.width,
        height: frame.height,
        dpr: frame.dpr,
        drawOne: () => [],
        extraCommands: mapped.commands,
      });

      overlay.width = Math.round(frame.width * frame.dpr);
      overlay.height = Math.round(frame.height * frame.dpr);
      overlay.style.width = `${frame.width}px`;
      overlay.style.height = `${frame.height}px`;
      ctx.setTransform(frame.dpr, 0, 0, frame.dpr, 0, 0);
      ctx.clearRect(0, 0, frame.width, frame.height);
      ctx.imageSmoothingEnabled = true;
      for (const cmd of cmds) drawResidue(ctx, cmd, sheets.img, palette);
    },
  };
}
