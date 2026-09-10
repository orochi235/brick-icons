/** `PaintCommand[]` as weasel `DrawCommand[]`, for the scene executor.
 *
 *  The two executors must receive the same list and draw the same pixels, or
 *  the timing compares two different amounts of work. Everything here mirrors
 *  `draw2d.ts` command for command; where it cannot, `unsupported` says so and
 *  the harness refuses to report that rung rather than reporting a renderer
 *  that was quick because it drew less.
 */
import {
  ellipsePath, rectPath,
  type DrawCommand,
} from '@weasel-js/core';
import { CIRCLE_SCALE } from '@lab/corpus/draw2d';
import { RETIRED_WASH, type PaintCommand } from '@lab/corpus/paint';

/** Every feature this mapping can decline to draw, named once.
 *
 *  Shared rather than spelled inline so the hybrid executor's second half can
 *  be checked against it at compile time: a name added here and nowhere else
 *  is a cell nothing paints. */
export const UNSUPPORTED = {
  badges: 'badges',
  strip: 'kind strip',
  captions: 'captions',
  caret: 'caret',
  sticker: 'sticker mark',
  glyph: 'category glyph',
  slash: 'slash',
  image: 'loose/vector image rung',
  label: 'band label',
} as const;

export interface Mapped {
  commands: DrawCommand[];
  /** Command features this mapping does not reproduce, each named once.
   *  A non-empty set makes the rung incomparable, never merely approximate. */
  unsupported: Set<string>;
}

function fillRect(x: number, y: number, w: number, h: number,
                  color: string, opacity?: number): DrawCommand {
  return { kind: 'path', path: rectPath(x, y, w, h), fill: { color, opacity } };
}

/** A stroke straddles its path, so the rect is inset by half the width --
 *  the same correction `strokeBorder` makes. */
function strokeRect(x: number, y: number, w: number, h: number,
                    color: string, width: number): DrawCommand {
  const i = width / 2;
  return {
    kind: 'path',
    path: rectPath(x + i, y + i, w - width, h - width),
    stroke: { paint: { color }, width },
  };
}

export type Sampling = 'nearest' | 'linear';

export function toDrawCommands(cmds: readonly PaintCommand[],
                               sheet: ImageBitmap | null,
                               sampling: Sampling = 'nearest'): Mapped {
  const out: DrawCommand[] = [];
  const unsupported = new Set<string>();

  const overlays = (cmd: { badges?: unknown[]; strip?: unknown[];
                           captions?: unknown[] }) => {
    if (cmd.badges?.length) unsupported.add(UNSUPPORTED.badges);
    if (cmd.strip?.length) unsupported.add(UNSUPPORTED.strip);
    if (cmd.captions?.length) unsupported.add(UNSUPPORTED.captions);
  };

  for (const cmd of cmds) {
    if (cmd.kind === 'sprite') {
      if (!sheet) continue;
      const alpha = cmd.alpha ?? 1;
      const body: DrawCommand[] = [
        fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh, cmd.ground),
        { kind: 'image', image: sheet, x: cmd.dx, y: cmd.dy, w: cmd.dw, h: cmd.dh,
          source: { x: cmd.sx, y: cmd.sy, w: cmd.sw, h: cmd.sh },
          // Linear reaches half a texel past `source` and bleeds the
          // neighboring tile into every cell edge; nearest does not, and on a
          // minified 5652px atlas it costs -- which is what the two settings
          // are here to separate.
          sampling },
      ];
      if (cmd.wash) {
        body.push(fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh, RETIRED_WASH, cmd.wash));
      }
      // Flat unless the alpha actually needs a group. A group per cell is a
      // state change per cell, which is the cost this renderer exists to
      // avoid -- and it would be charged to weasel rather than to the mapping.
      if (alpha === 1) out.push(...body);
      else out.push({ kind: 'group', alpha, children: body });
      overlays(cmd);
      if (cmd.caret) unsupported.add(UNSUPPORTED.caret);
    } else if (cmd.kind === 'image') {
      unsupported.add(UNSUPPORTED.image);
      overlays(cmd);
    } else if (cmd.kind === 'fill') {
      if (cmd.mark === 'sticker') {
        unsupported.add(UNSUPPORTED.sticker);
      } else if (cmd.glyph) {
        unsupported.add(UNSUPPORTED.glyph);
      } else if (cmd.shape === 'circle') {
        const iw = cmd.dw * CIRCLE_SCALE;
        const ih = cmd.dh * CIRCLE_SCALE;
        out.push({
          kind: 'path',
          path: ellipsePath({ x: cmd.dx + (cmd.dw - iw) / 2, y: cmd.dy + (cmd.dh - ih) / 2,
                              width: iw, height: ih }),
          fill: { color: cmd.fill },
        });
      } else {
        out.push(fillRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh, cmd.fill));
      }
      if (cmd.border && cmd.borderWidth > 0) {
        out.push(strokeRect(cmd.dx, cmd.dy, cmd.dw, cmd.dh, cmd.border, cmd.borderWidth));
        if (cmd.slash) unsupported.add(UNSUPPORTED.slash);
      }
      overlays(cmd);
      if (cmd.caret) unsupported.add(UNSUPPORTED.caret);
    } else if (cmd.kind === 'label') {
      // Deliberately undrawn. Weasel resolves a run through an MSDF atlas and
      // canvas2d through the platform rasterizer, so the two disagree on both
      // the glyphs and the advance widths -- and the wall's overlay layer is
      // already the place text is drawn. Naming it here is what stops a rung
      // carrying band labels from being reported as comparable.
      unsupported.add(UNSUPPORTED.label);
    }
  }

  return { commands: out, unsupported };
}
