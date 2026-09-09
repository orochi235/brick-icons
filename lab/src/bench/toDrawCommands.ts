/** `PaintCommand[]` as weasel `DrawCommand[]`, for the scene executor.
 *
 *  The two executors must receive the same list and draw the same pixels, or
 *  the timing compares two different amounts of work. Everything here mirrors
 *  `draw2d.ts` command for command; where it cannot, `unsupported` says so and
 *  the harness refuses to report that rung rather than reporting a renderer
 *  that was quick because it drew less.
 */
import {
  ellipsePath, rectPath, textCommand,
  type DrawCommand,
} from '@weasel-js/core';
import { RETIRED_WASH, type PaintCommand } from '@lab/corpus/paint';
import type { Palette } from '@lab/corpus/palette';

/** Kept in step with `draw2d.ts`, whose copies are module-private. */
const CIRCLE_SCALE = 0.6;

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
                               palette: Palette,
                               sampling: Sampling = 'nearest'): Mapped {
  const out: DrawCommand[] = [];
  const unsupported = new Set<string>();

  const overlays = (cmd: { badges?: unknown[]; strip?: unknown[];
                           captions?: unknown[] }) => {
    if (cmd.badges?.length) unsupported.add('badges');
    if (cmd.strip?.length) unsupported.add('kind strip');
    if (cmd.captions?.length) unsupported.add('captions');
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
      if (cmd.caret) unsupported.add('caret');
    } else if (cmd.kind === 'image') {
      unsupported.add('loose/vector image rung');
      overlays(cmd);
    } else if (cmd.kind === 'fill') {
      if (cmd.mark === 'sticker') {
        unsupported.add('sticker mark');
      } else if (cmd.glyph) {
        unsupported.add('category glyph');
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
        if (cmd.slash) unsupported.add('slash');
      }
      overlays(cmd);
      if (cmd.caret) unsupported.add('caret');
    } else if (cmd.kind === 'label') {
      const text = cmd.depth === 0
        ? `${cmd.text}  ${cmd.count.toLocaleString()}` : cmd.text;
      const color = cmd.depth === 0 ? palette.label.fill : palette.sublabel.fill;
      out.push(textCommand(cmd.dx, cmd.dy, text,
                           { fontSize: cmd.size, fill: { color } } as never));
      unsupported.add('band label metrics');
    }
  }

  return { commands: out, unsupported };
}
