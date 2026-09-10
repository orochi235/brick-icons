/** The A/B itself: two executors alive in one process, alternating paints.
 *
 *  Sequential runs -- all of A, then all of B -- measure the machine's mood and
 *  not the change. This repo has filed that twice, at 36x against 18x for one
 *  commit and at 0.90x for the same code on a peer's box. So the two renderers
 *  interleave, and a rung's pair of numbers comes from paints seconds apart at
 *  most.
 */
import type { Frame, WallRenderer } from '@lab/bench/renderers';
import type { PaintCommand } from '@lab/corpus/paint';

export interface Rung {
  /** On-screen cell size, which is what decides how much each cell draws. */
  cellPx: number;
  /** The baked sheet this rung's cells come from. The wall swaps sheets by
   *  cell size, so a rung pinned to the wrong one measures minification. */
  level: number;
  commands: PaintCommand[];
}

export interface Timing {
  name: string;
  /** Every paint, in order, so the reader can see warmup rather than have it
   *  averaged away. */
  ms: number[];
  median: number;
  /** Why this renderer's number is not the baseline's to compare against.
   *
   *  Per renderer rather than per rung: the hybrid draws the overlays and the
   *  bare scene renderer does not, so on a rung wearing badges one of them is
   *  comparable and the other is not. Withholding the rung would retire the
   *  measurement the hybrid exists to take. */
  withheld: string | null;
}

export interface RungResult {
  cellPx: number;
  level: number;
  commands: number;
  timings: Timing[];
}

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

/** A coarse fingerprint of what actually landed on a renderer's canvases.
 *
 *  WebGL2 silently no-ops without a context, and an executor that draws
 *  nothing is arbitrarily fast. Downsampling to a small grid keeps this immune
 *  to the antialias differences between two rasterizers while still catching a
 *  blank canvas or a missing layer. Must run in the same task as the paint: a
 *  WebGL drawing buffer is not preserved past it.
 *
 *  A renderer may paint into a stack -- the hybrid's overlays sit on a second
 *  canvas over its GL one -- and the stack is flattened at full resolution
 *  before the downsample. Shrinking each layer first and compositing the
 *  small ones is different arithmetic wherever the top layer's alpha varies
 *  across a probe cell, which for an overlay pass is everywhere it draws.
 */
const PROBE = 32;

function flatten(layers: readonly HTMLCanvasElement[],
                 first: HTMLCanvasElement): HTMLCanvasElement {
  if (layers.length === 1) return first;
  const flat = document.createElement('canvas');
  flat.width = first.width;
  flat.height = first.height;
  const ctx = flat.getContext('2d');
  if (!ctx) return first;
  for (const l of layers) ctx.drawImage(l, 0, 0, flat.width, flat.height);
  return flat;
}

export function fingerprint(layers: readonly HTMLCanvasElement[]): number[] | null {
  const first = layers[0];
  if (!first) return null;
  const probe = document.createElement('canvas');
  probe.width = PROBE;
  probe.height = PROBE;
  const ctx = probe.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;
  try {
    ctx.drawImage(flatten(layers, first), 0, 0, PROBE, PROBE);
  } catch {
    return null;
  }
  const { data } = ctx.getImageData(0, 0, PROBE, PROBE);
  const out: number[] = [];
  for (let i = 0; i < data.length; i += 4) {
    // Premultiplied against the ground both sides clear to, so a transparent
    // canvas and a white one do not read alike.
    out.push(((data[i]! + data[i + 1]! + data[i + 2]!) / 3) * (data[i + 3]! / 255));
  }
  return out;
}

export function isBlank(fp: number[] | null): boolean {
  if (!fp) return true;
  return fp.every((v) => v === fp[0]);
}

/** Mean absolute difference per channel, 0..255. */
export function drift(a: number[], b: number[]): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += Math.abs(a[i]! - b[i]!);
  return sum / a.length;
}

/** How far two rasterizers may differ before the rung stops being a fair
 *  comparison. Antialiasing and gamma differ between Canvas2D and GL; a
 *  missing badge or an undrawn layer does not hide under this. */
export const DRIFT_LIMIT = 12;

export interface RunOptions<R extends Rung = Rung> {
  rungs: R[];
  /** Built per rung: each draws from its own level's sheet. */
  renderersFor: (rung: R) => WallRenderer[];
  frame: Frame;
  /** Paints per renderer per rung, after the discarded warmup. */
  reps?: number;
  onLine?: (line: string) => void;
}

export function runBench<R extends Rung>({ rungs, renderersFor, frame, reps = 7,
                                          onLine = () => {} }: RunOptions<R>):
                                          RungResult[] {
  const results: RungResult[] = [];

  for (const rung of rungs) {
    const renderers = renderersFor(rung);
    const ms = new Map<string, number[]>(renderers.map((r) => [r.name, []]));
    const prints = new Map<string, number[] | null>();
    const missing = new Map<string, ReadonlySet<string>>();

    // Warmup is its own pass and is thrown away: the first paint of a rung
    // uploads textures and compiles programs, and neither recurs. The readback
    // rides the same task, since a WebGL drawing buffer does not survive it.
    for (const r of renderers) {
      r.paint(rung.commands, frame);
      prints.set(r.name, fingerprint(r.layers));
    }

    for (let i = 0; i < reps; i++) {
      for (const r of renderers) {
        const t0 = performance.now();
        r.paint(rung.commands, frame);
        ms.get(r.name)!.push(performance.now() - t0);
      }
    }

    for (const r of renderers) missing.set(r.name, r.unsupported);

    // The first renderer is the control every other is read against, so its
    // own failure takes the whole rung with it.
    const base = prints.get(renderers[0]!.name) ?? null;
    const baseFailed = isBlank(base)
      ? `${renderers[0]!.name} drew nothing` : null;

    const withheldFor = (r: WallRenderer): string | null => {
      if (baseFailed) return baseFailed;
      const gaps = missing.get(r.name)!;
      if (gaps.size) return `does not draw: ${[...gaps].join(', ')}`;
      const fp = prints.get(r.name) ?? null;
      // Cheap to state and the one that would otherwise pass silently: a
      // renderer with no context draws nothing in no time at all.
      if (isBlank(fp)) return 'drew nothing';
      if (r === renderers[0]) return null;
      const d = drift(base!, fp!);
      return d > DRIFT_LIMIT
        ? `differs by ${d.toFixed(1)}, over the ${DRIFT_LIMIT} limit` : null;
    };

    const timings: Timing[] = renderers.map((r) => ({
      name: r.name, ms: ms.get(r.name)!, median: median(ms.get(r.name)!),
      withheld: withheldFor(r),
    }));

    results.push({
      cellPx: rung.cellPx, level: rung.level, commands: rung.commands.length,
      timings,
    });

    onLine(`${results.length}/${rungs.length}  cell ${rung.cellPx}px  `
      + `level ${rung.level}  `
      + `${rung.commands.length} commands  `
      + timings.map((t) => `${t.name} ${t.median.toFixed(1)}ms`
        + (t.withheld ? ` [${t.withheld}]` : '')).join('  '));
  }

  return results;
}
