/** Putting the 3D pane in the same viewport as the 2D ones.
 *
 * A 2D pane draws its SVG at `width:100%` with `preserveAspectRatio="xMidYMid
 * meet"`, inside a stage the shared camera transforms as `translate(pan)
 * scale(zoom)` about origin 0,0. This reproduces that as an orthographic
 * frustum, so the same world point lands on the same pixel in both.
 *
 * The world -> viewBox map is the render's own, read from the `.fit.json` the
 * CLI writes beside the SVG; nothing here re-derives it.
 */
import type { Camera } from '@lab/panes/camera';

export type Vec3Tuple = [number, number, number];

/** `<name>.fit.json`: the engine's view basis and its world -> viewBox affine. */
export interface RenderFit {
  right: Vec3Tuple;
  up: Vec3Tuple;
  fwd: Vec3Tuple;
  /** Uniform scale and offset from projected A/B to viewBox units. */
  k: number;
  kx: number;
  ky: number;
  width: number;
  height: number;
  /** The style's VIEW-space light direction, pointing at the source. Absent
   *  for a render with no style -- wireframe, or `--shade-style none`. */
  light?: Vec3Tuple;
  /** The style's resolved part colour, as r/g/b 0-255. Absent with `light`. */
  part_color?: Vec3Tuple;
}

export interface Box {
  width: number;
  height: number;
}

/** Screen y is down and B is the projected down-axis, so this is one uniform
 *  scale and a translation -- never a flip. */
export interface ScreenMap {
  scale: number;
  x: number;
  y: number;
}

export interface Frustum {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export function isRenderFit(value: unknown): value is RenderFit {
  if (!value || typeof value !== 'object') return false;
  const f = value as Record<string, unknown>;
  const vec = (v: unknown) => Array.isArray(v) && v.length === 3
    && v.every((n) => typeof n === 'number' && Number.isFinite(n));
  const num = (n: unknown): n is number => typeof n === 'number' && Number.isFinite(n);
  return vec(f.right) && vec(f.up) && vec(f.fwd)
    && num(f.k) && f.k !== 0 && num(f.kx) && num(f.ky)
    && num(f.width) && f.width > 0 && num(f.height) && f.height > 0;
}

/** viewBox units -> body pixels, as `xMidYMid meet` letterboxes them. */
export function letterbox(fit: RenderFit, box: Box): ScreenMap {
  const scale = Math.min(box.width / fit.width, box.height / fit.height);
  return {
    scale,
    x: (box.width - fit.width * scale) / 2,
    y: (box.height - fit.height * scale) / 2,
  };
}

/** Projected A/B -> body pixels: the letterbox with the shared camera over it. */
export function screenMap(fit: RenderFit, box: Box, camera: Camera): ScreenMap {
  const fitted = letterbox(fit, box);
  const scale = fit.k * fitted.scale * camera.zoom;
  return {
    scale,
    x: (fit.kx * fitted.scale + fitted.x) * camera.zoom + camera.pan.x,
    y: (fit.ky * fitted.scale + fitted.y) * camera.zoom + camera.pan.y,
  };
}

export function toScreen(map: ScreenMap, a: number, b: number): { x: number; y: number } {
  return { x: a * map.scale + map.x, y: b * map.scale + map.y };
}

export function fromScreen(map: ScreenMap, x: number, y: number): { a: number; b: number } {
  return { a: (x - map.x) / map.scale, b: (y - map.y) / map.scale };
}

/** The orthographic bounds that draw that map into a `box`-sized canvas.
 *
 * Camera-up is +(P.up) while B is its negation, so the vertical bounds are
 * B's negated and swapped: the body's top edge is the larger one.
 */
export function frustum(fit: RenderFit, box: Box, camera: Camera): Frustum {
  const map = screenMap(fit, box, camera);
  const topLeft = fromScreen(map, 0, 0);
  const bottomRight = fromScreen(map, box.width, box.height);
  return {
    left: topLeft.a,
    right: bottomRight.a,
    top: -topLeft.b,
    bottom: -bottomRight.b,
  };
}

/** Where the camera sits to look at `target` along the render's view axis. */
export function eyeFor(fit: RenderFit, target: Vec3Tuple, distance: number): Vec3Tuple {
  return [
    target[0] - fit.fwd[0] * distance,
    target[1] - fit.fwd[1] * distance,
    target[2] - fit.fwd[2] * distance,
  ];
}

/** What the trial's config asks of the 3D pane's drawing rather than of its
 *  camera. Every field is a CLI flag with a direct three.js counterpart;
 *  `--shading`, `--shade-style` and `--curve-quality` have none, because the
 *  pane draws the model rather than the engine's rendering of it. */
export interface ThreeStyle {
  opacity: number;
  /** `--line-width`, in viewBox units; `strokePx` puts it in screen pixels. */
  lineWidth: number;
  /** `--svg-bg`, or null for the transparent `none`. */
  background: string | null;
}

const DEFAULT_STYLE: ThreeStyle = { opacity: 1, lineWidth: 2, background: null };

export function threeStyle(config: Record<string, unknown>): ThreeStyle {
  const num = (key: string, fallback: number) => {
    const v = config[key];
    return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
  };
  const bg = config.svg_bg;
  return {
    opacity: Math.min(1, Math.max(0, num('opacity', DEFAULT_STYLE.opacity))),
    lineWidth: Math.max(0, num('line_width', DEFAULT_STYLE.lineWidth)),
    // `none` is the CLI's word for a transparent ground, not a colour.
    background: typeof bg === 'string' && bg && bg !== 'none' ? bg : null,
  };
}

/** A stroke authored in viewBox units, in screen pixels.
 *
 * The 2D panes are CSS-scaled, so their strokes grow with the zoom; matching
 * that is what keeps the weights comparable through a zoom rather than only at
 * rest. Without a fit there is nothing to scale by and the width stands as
 * given. */
export function strokePx(fit: RenderFit | null, box: Box, camera: Camera,
                         width: number): number {
  if (!fit) return width;
  return Math.max(0.5, width * letterbox(fit, box).scale * camera.zoom);
}

/** Where to stand a directional light so it shines the way the render's did.
 *
 * The fit's `light` is view-space (right, up, depth) and points AT the source,
 * which is also what three.js wants of a directional light's position. */
export function lightPosition(fit: RenderFit | null,
                              distance: number): Vec3Tuple | null {
  if (!fit?.light) return null;
  const [lx, ly, lz] = fit.light;
  return toThree([
    (fit.right[0] * lx + fit.up[0] * ly + fit.fwd[0] * lz) * distance,
    (fit.right[1] * lx + fit.up[1] * ly + fit.fwd[1] * lz) * distance,
    (fit.right[2] * lx + fit.up[2] * ly + fit.fwd[2] * lz) * distance,
  ]);
}

/** The render's part colour as a three.js hex, or null to leave the part in
 *  the colours the LDraw file gave it. */
export function partColorHex(fit: RenderFit | null): number | null {
  if (!fit?.part_color) return null;
  const [r, g, b] = fit.part_color;
  return (r << 16) | (g << 8) | b;
}

/** A vector in LDraw space, in the pane's world.
 *
 * The part is drawn under `rotation.x = PI` (LDraw's Y points down), so a
 * direction from the fit needs the same turn before a three.js camera can use
 * it. Everything the fit carries is LDraw's; everything the pane holds is
 * turned.
 */
export function toThree(v: Vec3Tuple): Vec3Tuple {
  return [v[0], -v[1], -v[2]];
}
