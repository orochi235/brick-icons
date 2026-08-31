/** The camera angle, in the terms `--angle` uses.
 *
 * Latitude is elevation, positive up; longitude is azimuth, positive to the
 * right. The presets are `brick_icons/render.py`'s, copied here because the
 * CLI accepts them as `--angle` values and the 3D pane must show the same
 * view they name.
 */
export interface Angle {
  lat: number;
  long: number;
}

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

const PRESETS: Record<string, Angle> = {
  iso: { lat: 30, long: 45 },
  front: { lat: 0, long: 0 },
  back: { lat: 0, long: 180 },
  left: { lat: 0, long: -90 },
  right: { lat: 0, long: 90 },
  top: { lat: 90, long: 0 },
  bottom: { lat: -90, long: 0 },
};

const RAD = Math.PI / 180;

export function parseAngle(text: string): Angle | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const preset = PRESETS[trimmed];
  if (preset) return { ...preset };
  const parts = trimmed.split(',').map((p) => Number(p.trim()));
  if (parts.length !== 2 || parts.some((n) => !Number.isFinite(n))) return null;
  return { lat: parts[0]!, long: parts[1]! };
}

function wrapLong(long: number): number {
  return ((long + 180) % 360 + 360) % 360 - 180;
}

export function formatAngle(angle: Angle): string {
  const lat = Math.round(Math.min(90, Math.max(-90, angle.lat)));
  return `${lat},${Math.round(wrapLong(angle.long))}`;
}

/** Where the camera sits for an angle, with +Y up and the part at the origin. */
export function orbitFromAngle(angle: Angle, radius: number): Vec3 {
  const lat = angle.lat * RAD;
  const long = angle.long * RAD;
  return {
    x: radius * Math.cos(lat) * Math.sin(long),
    y: radius * Math.sin(lat),
    z: radius * Math.cos(lat) * Math.cos(long),
  };
}

export function angleFromOrbit(position: Vec3): Angle {
  const radius = Math.hypot(position.x, position.y, position.z) || 1;
  return {
    lat: Math.asin(position.y / radius) / RAD,
    long: Math.atan2(position.x, position.z) / RAD,
  };
}
