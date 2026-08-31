# Lab Reference and 3D Panes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two more panes beside the engines — LDView's render as ground truth, and an interactive 3D view you can orbit. Orbiting sets `--angle` for every other pane, and when the orbit settles LDView re-renders at that exact latitude and longitude.

**Architecture:** The reference is an LDView subprocess per frame, so it is cached by angle and fired only when an orbit settles. The 3D pane is three.js `LDrawLoader` reading the same `.dat` from the server's `/ldraw` mount — an independent parse, labeled as such. The conversion between an orbit and `--angle` is a plain module with tests, because a sign error there looks like a rendering bug everywhere else.

**Tech Stack:** Python (the reference route); React 19, three.js, `@react-three/fiber`, `@react-three/drei`, Vitest.

**Depends on:** `2026-08-31-lab-server.md` and `2026-08-31-lab-part-inspector.md`. `brick_icons/render.py` already drives LDView via `render_part`, and `sources.ts` already declares `reference` and `3d`.

**Spec:** `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`

---

## What is true about the coordinates

Two conventions meet in this plan, and both are traps.

**LDView's `-DefaultLatLong=lat,long`.** `brick_icons/render.py` names the
presets: `top` is `(90, 0)`, `bottom` is `(-90, 0)`, `front` is `(0, 0)`,
`right` is `(0, 90)`, `left` is `(0, -90)`, `iso` is `(30, 45)`. So latitude is
elevation, positive upward, and longitude is azimuth, positive to the right.

**LDraw's Y axis points down.** A part's studs are at *negative* Y. three.js
treats +Y as up, so a model loaded straight from `LDrawLoader` appears upside
down unless the scene flips it. Task 5's walkthrough is what catches this;
`LDrawLoader`'s own three.js example applies the flip, and so must we.

---

## File Structure

| file | responsibility |
|---|---|
| `brick_icons/lab/reference.py` | LDView renders, cached by angle |
| `brick_icons/lab/app.py` (modify) | `GET /api/reference` |
| `lab/src/panes/orbit.ts` | orbit ↔ `--angle` |
| `lab/src/panes/ThreePane.tsx` | the three.js view |
| `lab/src/panes/useReference.ts` | fetch the LDView frame for the current angle |
| `lab/src/instruments/partInspector.tsx` (modify) | wire both panes in |

---

## Task 1: LDView renders, cached

**Files:**
- Create: `brick_icons/lab/reference.py`
- Test: `tests/test_lab_reference.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lab_reference.py`:

```python
"""LDView is a subprocess per frame, so a reference is cached by everything
that changes the picture and by nothing else."""
import pytest

from brick_icons.lab import reference


def test_same_request_gives_the_same_key():
    a = reference.key("3941", "30,25", 900, None)
    b = reference.key("3941", "30,25", 900, None)
    assert a == b


def test_angle_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "45,45", 900, None)


def test_colour_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "30,25", 900, "0xc91a09")


def test_resolution_changes_the_key():
    assert reference.key("3941", "30,25", 900, None) \
        != reference.key("3941", "30,25", 1200, None)


def test_key_is_filesystem_safe():
    k = reference.key("3941", "30,25", 900, "0xc91a09")
    assert k.isalnum() and len(k) == 16


def test_renders_a_part(tmp_path, ldraw_dir):
    if not reference.available("."):
        pytest.skip("LDView not installed; run scripts/setup-ldview.sh")
    got = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert got["ok"], got["error"]
    assert (tmp_path / got["key"] / got["name"]).exists()


def test_second_request_is_cached(tmp_path, ldraw_dir):
    if not reference.available("."):
        pytest.skip("LDView not installed; run scripts/setup-ldview.sh")
    reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    again = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert again["cached"] is True


def test_a_missing_ldview_is_a_message_not_a_traceback(tmp_path, monkeypatch):
    monkeypatch.setattr(reference, "available", lambda root: False)
    got = reference.render_reference("3005", "30,25", root=".", cache_root=tmp_path)
    assert got["ok"] is False
    assert "setup-ldview" in got["error"]


def test_a_bad_angle_is_reported(tmp_path):
    got = reference.render_reference("3005", "not-an-angle", root=".", cache_root=tmp_path)
    assert got["ok"] is False
    assert "angle" in got["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_reference.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brick_icons.lab.reference'`

- [ ] **Step 3: Write the implementation**

Create `brick_icons/lab/reference.py`:

```python
"""LDView renders, for the reference pane.

LDView writes a snapshot per invocation, so every frame is a subprocess. That
is why this caches on everything that changes the picture, and why the pane
asks for a frame only when an orbit settles rather than while it moves.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .. import render
from ..config import load_config


def key(part: str, angle: str, render_px: int, part_color: str | None) -> str:
    blob = "\x00".join([part, angle, str(render_px), part_color or ""])
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def available(root: Path | str = ".") -> bool:
    """Whether the vendored LDView is actually present."""
    return Path(load_config(root=str(root)).ldview).exists()


def render_reference(part: str, angle: str, root: Path | str = ".",
                     cache_root: Path | str = "out/lab/reference",
                     render_px: int | None = None,
                     part_color: str | None = None) -> dict:
    cfg = load_config(root=str(root))
    px = render_px or cfg.render_px
    cache_key = key(part, angle, px, part_color)
    name = f"{part}.png"
    out = Path(cache_root) / cache_key / name

    def failed(message: str) -> dict:
        return {"ok": False, "cached": False, "key": cache_key, "name": name,
                "error": message}

    try:
        render.resolve_latlong(angle)
    except ValueError as e:
        return failed(str(e))

    if out.exists():
        return {"ok": True, "cached": True, "key": cache_key, "name": name,
                "error": None}
    if not available(root):
        return failed("LDView is not installed — run scripts/setup-ldview.sh")

    overrides = {"angle": angle, "render_px": px}
    if part_color:
        overrides["part_color"] = part_color
    cfg = load_config(root=str(root), overrides=overrides)
    try:
        render.render_part(cfg, part, out)
    except Exception as e:                          # noqa: BLE001
        return failed(f"{type(e).__name__}: {e}")
    return {"ok": True, "cached": False, "key": cache_key, "name": name,
            "error": None}
```

The public name is `render_reference`, not `render`: this module already
imports `brick_icons.render`, and a function shadowing it would make
`render.render_part` below unreachable.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_reference.py -v`
Expected: PASS, 9 tests (two skip if LDView is absent). If `load_config` does
not accept an `overrides` dict with these keys, read its signature in
`brick_icons/config.py` and pass what it takes.

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/reference.py tests/test_lab_reference.py
git commit -m "cache LDView reference renders by angle"
```

---

## Task 2: The reference route

**Files:**
- Modify: `brick_icons/lab/app.py`
- Test: `tests/test_lab_app.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_lab_app.py`:

```python
def test_reference_route_reports_a_bad_angle(client):
    r = client.get("/api/reference", params={"part": "3005", "angle": "nope"})
    assert r.status_code == 400


def test_reference_route_returns_a_url_when_it_can_render(client, ldraw_dir):
    from brick_icons.lab import reference
    if not reference.available("."):
        pytest.skip("LDView not installed")
    body = client.get("/api/reference",
                      params={"part": "3005", "angle": "30,25"}).json()
    assert body["url"].startswith("/api/reference-artifact/")
    assert client.get(body["url"]).status_code == 200


def test_reference_route_says_when_ldview_is_missing(client, monkeypatch):
    from brick_icons.lab import reference
    monkeypatch.setattr(reference, "available", lambda root: False)
    r = client.get("/api/reference", params={"part": "3005", "angle": "30,25"})
    assert r.status_code == 503
    assert "setup-ldview" in r.json()["detail"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_lab_app.py -k reference -v`
Expected: FAIL with 404

- [ ] **Step 3: Write the implementation**

In `brick_icons/lab/app.py`, add `reference` to the `from . import ...` line,
add to `create_app` beside the other state:

```python
    app.state.reference_root = Path(cache_root) / "reference"
```

and add the routes:

```python
    @app.get("/api/reference")
    def get_reference(part: str, angle: str, render_px: int | None = None,
                      part_color: str | None = None):
        got = reference.render_reference(
            part, angle, root=root, cache_root=app.state.reference_root,
            render_px=render_px, part_color=part_color)
        if not got["ok"]:
            code = 503 if "not installed" in (got["error"] or "") else 400
            raise HTTPException(code, got["error"])
        return {**got, "url": f"/api/reference-artifact/{got['key']}/{got['name']}"}

    @app.get("/api/reference-artifact/{key}/{name}")
    def get_reference_artifact(key: str, name: str):
        if not key.isalnum() or "/" in name or ".." in name:
            raise HTTPException(400, "bad artifact path")
        path = app.state.reference_root / key / name
        if not path.is_file():
            raise HTTPException(404, "no such reference")
        return FileResponse(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_lab_app.py -v`
Expected: PASS (the two LDView tests skip if it is absent)

- [ ] **Step 5: Commit**

```bash
git add brick_icons/lab/app.py tests/test_lab_app.py
git commit -m "serve LDView reference frames"
```

---

## Task 3: Orbit ↔ angle

**Files:**
- Create: `lab/src/panes/orbit.ts`
- Test: `lab/src/panes/orbit.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/panes/orbit.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { angleFromOrbit, orbitFromAngle, parseAngle, formatAngle } from '@lab/panes/orbit';

describe('parseAngle', () => {
  it('reads a lat,long pair', () => {
    expect(parseAngle('30,25')).toEqual({ lat: 30, long: 25 });
  });

  it('reads the named presets the CLI accepts', () => {
    expect(parseAngle('iso')).toEqual({ lat: 30, long: 45 });
    expect(parseAngle('top')).toEqual({ lat: 90, long: 0 });
    expect(parseAngle('bottom')).toEqual({ lat: -90, long: 0 });
    expect(parseAngle('left')).toEqual({ lat: 0, long: -90 });
  });

  it('tolerates spaces', () => {
    expect(parseAngle(' 30 , 25 ')).toEqual({ lat: 30, long: 25 });
  });

  it('is null for nonsense, so a caller can leave the angle alone', () => {
    expect(parseAngle('sideways')).toBeNull();
    expect(parseAngle('')).toBeNull();
  });
});

describe('formatAngle', () => {
  it('writes what the CLI parses', () => {
    expect(formatAngle({ lat: 30, long: 25 })).toBe('30,25');
  });

  it('rounds, because a drag produces fractions the CLI does not need', () => {
    expect(formatAngle({ lat: 30.4, long: 24.6 })).toBe('30,25');
  });

  it('normalizes longitude into -180..180', () => {
    expect(formatAngle({ lat: 0, long: 190 })).toBe('0,-170');
    expect(formatAngle({ lat: 0, long: -190 })).toBe('0,170');
  });

  it('clamps latitude to the poles', () => {
    expect(formatAngle({ lat: 120, long: 0 })).toBe('90,0');
  });
});

describe('orbitFromAngle', () => {
  it('puts the camera above the part for the top view', () => {
    const p = orbitFromAngle({ lat: 90, long: 0 }, 100);
    expect(p.y).toBeCloseTo(100);
    expect(p.x).toBeCloseTo(0);
    expect(p.z).toBeCloseTo(0);
  });

  it('puts the camera in front for the front view', () => {
    const p = orbitFromAngle({ lat: 0, long: 0 }, 100);
    expect(p.z).toBeCloseTo(100);
    expect(p.y).toBeCloseTo(0);
  });

  it('puts the camera to the right for the right view', () => {
    const p = orbitFromAngle({ lat: 0, long: 90 }, 100);
    expect(p.x).toBeCloseTo(100);
    expect(p.z).toBeCloseTo(0);
  });

  it('keeps the radius', () => {
    const p = orbitFromAngle({ lat: 30, long: 45 }, 250);
    expect(Math.hypot(p.x, p.y, p.z)).toBeCloseTo(250);
  });
});

describe('angleFromOrbit', () => {
  it('inverts orbitFromAngle', () => {
    for (const angle of [{ lat: 30, long: 25 }, { lat: 0, long: 0 },
                         { lat: -45, long: 120 }, { lat: 60, long: -30 }]) {
      const back = angleFromOrbit(orbitFromAngle(angle, 100));
      expect(back.lat).toBeCloseTo(angle.lat);
      expect(back.long).toBeCloseTo(angle.long);
    }
  });

  it('is stable through a format round trip', () => {
    const text = formatAngle(angleFromOrbit(orbitFromAngle({ lat: 30, long: 45 }, 100)));
    expect(text).toBe('30,45');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/orbit.test.ts`
Expected: FAIL — cannot resolve `@lab/panes/orbit`

- [ ] **Step 3: Write the implementation**

Create `lab/src/panes/orbit.ts`:

```ts
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
  const wrapped = ((long + 180) % 360 + 360) % 360 - 180;
  return wrapped;
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/orbit.test.ts`
Expected: PASS, 14 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/panes/orbit.ts lab/src/panes/orbit.test.ts
git commit -m "convert between an orbit and the CLI's --angle"
```

---

## Task 4: The reference source

**Files:**
- Create: `lab/src/panes/useReference.ts`
- Modify: `lab/src/api/client.ts`
- Test: `lab/src/panes/useReference.test.ts`

- [ ] **Step 1: Write the failing test**

Create `lab/src/panes/useReference.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { referenceState } from '@lab/panes/useReference';

describe('referenceState', () => {
  it('is idle without a part', () => {
    expect(referenceState({ part: '', url: null, error: null, loading: false }))
      .toEqual({ kind: 'idle' });
  });

  it('is running while a frame is in flight', () => {
    expect(referenceState({ part: '3941', url: null, error: null, loading: true }))
      .toEqual({ kind: 'running' });
  });

  it('is an image once a frame arrives', () => {
    expect(referenceState({ part: '3941', url: '/api/reference-artifact/k/3941.png',
                            error: null, loading: false }))
      .toEqual({ kind: 'image', src: '/api/reference-artifact/k/3941.png' });
  });

  it('reports a missing LDView as the pane\'s error', () => {
    expect(referenceState({ part: '3941', url: null, loading: false,
                            error: 'LDView is not installed — run scripts/setup-ldview.sh' }))
      .toEqual({ kind: 'error',
                 message: 'LDView is not installed — run scripts/setup-ldview.sh' });
  });

  it('prefers the error over a stale frame', () => {
    expect(referenceState({ part: '3941', url: '/old.png', error: 'boom', loading: false }).kind)
      .toBe('error');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd lab && npx vitest run src/panes/useReference.test.ts`
Expected: FAIL — cannot resolve `@lab/panes/useReference`

- [ ] **Step 3: Write the implementation**

Add to `lab/src/api/client.ts`, inside the returned object:

```ts
    async reference(part: string, angle: string, partColor?: string) {
      const params = new URLSearchParams({ part, angle });
      if (partColor) params.set('part_color', partColor);
      return json<{ url: string; cached: boolean }>(
        fetchImpl, at(`/api/reference?${params}`));
    },
```

Create `lab/src/panes/useReference.ts`:

```ts
import { useEffect, useState } from 'react';
import type { LabClient } from '@lab/api/client';
import type { PaneState } from '@lab/panes/SourcePane';

export interface ReferenceStatus {
  part: string;
  url: string | null;
  error: string | null;
  loading: boolean;
}

export function referenceState(status: ReferenceStatus): PaneState {
  if (!status.part.trim()) return { kind: 'idle' };
  if (status.error) return { kind: 'error', message: status.error };
  if (status.loading) return { kind: 'running' };
  if (status.url) return { kind: 'image', src: status.url };
  return { kind: 'idle' };
}

/** One LDView frame for the current part and angle.
 *
 * Keyed on the settled angle rather than on the live orbit: LDView is a
 * subprocess per frame, so asking on every pointer move would queue hundreds.
 */
export function useReference(client: LabClient, part: string, angle: string,
                             partColor?: string): PaneState {
  const [status, setStatus] = useState<ReferenceStatus>({
    part, url: null, error: null, loading: false,
  });

  useEffect(() => {
    if (!part.trim() || !angle.trim()) {
      setStatus({ part, url: null, error: null, loading: false });
      return;
    }
    let live = true;
    setStatus((prev) => ({ ...prev, part, loading: true, error: null }));
    client.reference(part, angle, partColor)
      .then((got) => {
        if (live) setStatus({ part, url: got.url, error: null, loading: false });
      })
      .catch((e: Error) => {
        if (live) setStatus({ part, url: null, error: e.message, loading: false });
      });
    return () => { live = false; };
  }, [client, part, angle, partColor]);

  return referenceState(status);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd lab && npx vitest run src/panes/useReference.test.ts`
Expected: PASS, 5 tests

- [ ] **Step 5: Commit**

```bash
git add lab/src/panes/useReference.ts lab/src/panes/useReference.test.ts lab/src/api/client.ts
git commit -m "fetch the LDView frame for the current angle"
```

---

## Task 5: The 3D pane

**Files:**
- Create: `lab/src/panes/ThreePane.tsx`
- Modify: `lab/package.json`
- Test: manual (Task 7)

Three.js in jsdom needs a WebGL context that jsdom does not have, so this
component is verified in a browser rather than by a unit test. Everything about
it that *can* be tested without one — the angle conversion — is Task 3.

- [ ] **Step 1: Install the dependencies**

Run: `cd lab && npm install three@^0.170.0 @react-three/fiber@^9 @react-three/drei@^9 && npm install -D @types/three@^0.170.0`
Expected: all four install. If `@react-three/fiber` 9 refuses React 19, read
the peer range it reports and install the version that accepts React 19 — do
not downgrade React.

- [ ] **Step 2: Write the component**

Create `lab/src/panes/ThreePane.tsx`:

```tsx
import { Suspense, useEffect, useMemo, useRef } from 'react';
import { Canvas, useLoader, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { LDrawLoader } from 'three/examples/jsm/loaders/LDrawLoader.js';
import * as THREE from 'three';
import { angleFromOrbit, formatAngle, orbitFromAngle, parseAngle } from '@lab/panes/orbit';

const RADIUS = 240;

function Part({ part }: { part: string }) {
  const model = useLoader(LDrawLoader, `/ldraw/parts/${part}.dat`, (loader) => {
    // LDrawLoader resolves subfile references against this root.
    (loader as unknown as { setPartsLibraryPath: (p: string) => void })
      .setPartsLibraryPath('/ldraw/');
  });

  const object = useMemo(() => {
    const group = model.clone();
    // LDraw's Y axis points down: studs are at negative Y. Without this flip
    // the part hangs upside down and every angle reads inverted.
    group.rotation.x = Math.PI;
    const box = new THREE.Box3().setFromObject(group);
    const centre = box.getCenter(new THREE.Vector3());
    group.position.sub(centre);
    return group;
  }, [model]);

  return <primitive object={object} />;
}

function Camera({ angle, onSettle }: { angle: string; onSettle: (a: string) => void }) {
  const { camera } = useThree();
  const controls = useRef<{ addEventListener: (t: string, f: () => void) => void } | null>(null);

  useEffect(() => {
    const parsed = parseAngle(angle);
    if (!parsed) return;
    const p = orbitFromAngle(parsed, RADIUS);
    camera.position.set(p.x, p.y, p.z);
    camera.lookAt(0, 0, 0);
  }, [angle, camera]);

  return (
    <OrbitControls
      ref={controls as never}
      enablePan={false}
      // `end` fires when the drag stops, which is when LDView is worth firing.
      onEnd={() => onSettle(formatAngle(angleFromOrbit(camera.position)))}
    />
  );
}

export interface ThreePaneProps {
  part: string;
  angle: string;
  onSettle: (angle: string) => void;
}

export function ThreePane({ part, angle, onSettle }: ThreePaneProps) {
  if (!part.trim()) return <p>no part chosen</p>;
  return (
    <Canvas camera={{ fov: 35, near: 1, far: 4000 }}>
      <ambientLight intensity={0.7} />
      <directionalLight position={[-1, 1, 2]} intensity={1.2} />
      <Suspense fallback={null}>
        <Part part={part} />
      </Suspense>
      <Camera angle={angle} onSettle={onSettle} />
    </Canvas>
  );
}
```

- [ ] **Step 3: Keep it out of the unit test run**

The component imports WebGL code that jsdom cannot execute. Add to
`lab/vite.config.ts` under `test`:

```ts
    exclude: ['**/node_modules/**', '**/ThreePane*'],
```

- [ ] **Step 4: Confirm the app still builds**

Run: `cd lab && npm run build && npm run typecheck`
Expected: both succeed. If `three/examples/jsm/...` has no types, add
`"types": ["three"]` or import from `three/addons/loaders/LDrawLoader.js`,
whichever the installed version ships.

- [ ] **Step 5: Commit**

```bash
git add lab/src/panes/ThreePane.tsx lab/package.json lab/package-lock.json lab/vite.config.ts
git commit -m "add the three.js LDraw pane"
```

---

## Task 6: Wire both panes into the instrument

**Files:**
- Modify: `lab/src/instruments/partInspector.tsx`

- [ ] **Step 1: Render the two new sources**

In `lab/src/instruments/partInspector.tsx`, add the imports:

```tsx
import { ThreePane } from '@lab/panes/ThreePane';
import { useReference } from '@lab/panes/useReference';
```

Inside `Panes`, above the return:

```tsx
  const angle = String(config.angle ?? 'iso');
  const referencePane = useReference(client, part, angle,
                                     config.part_color as string | undefined);
```

Replace the pane loop so a non-engine source renders its own body. A source
that is not an engine has no SVG artifact, so it passes its content as the
pane's `overlay` and leaves the stage empty:

```tsx
      {sources.map((source) => {
        if (source.kind === '3d') {
          return (
            <SourcePane
              key={source.id}
              source={source}
              state={{ kind: 'idle' }}
              camera={camera}
              onCamera={() => {}}
              overlay={
                <ThreePane
                  part={part}
                  angle={angle}
                  onSettle={(next) => ctx.setConfig('angle', next)}
                />
              }
            />
          );
        }
        if (source.kind === 'reference') {
          return (
            <SourcePane key={source.id} source={source} state={referencePane}
              camera={camera} onCamera={(next) => ctx.trial.setView(next)} />
          );
        }
        return (/* the existing engine pane, unchanged */);
      })}
```

The 3D pane ignores the shared 2D camera: it has its own, and `enablePan` is
off so its only control is the orbit that writes `--angle`.

- [ ] **Step 2: Typecheck and test**

Run: `cd lab && npm run typecheck && npx vitest run`
Expected: PASS. `ctx.setConfig` is on the labkit `RenderContext`; if the
instrument's render signature does not expose it, read `RenderContext` in
`node_modules/@weasel-js/labkit/dist/index.d.ts` and use what it does.

- [ ] **Step 3: Commit**

```bash
git add lab/src/instruments/partInspector.tsx
git commit -m "show the reference and 3D panes beside the engines"
```

---

## Task 7: See it work

**Files:** none — verification, and the only check on the two coordinate
conventions this plan warned about.

- [ ] **Step 1: Make sure LDView is installed**

Run: `ls vendor/LDView.app` — if absent, `scripts/setup-ldview.sh`.

- [ ] **Step 2: Start both servers and open a part**

Run `.venv/bin/python -m brick_icons.lab &` and `cd lab && npm run dev`, then
open `3001` (a 2x4 brick — its studs make orientation obvious).

- [ ] **Step 3: Check the two traps**

Turn on the `3d` and `reference` sources. Confirm:

1. **The part is not upside down.** `3001`'s studs point up. If they point
   down, the LDraw Y-flip in `ThreePane` is wrong or missing.
2. **The named views agree.** Set `--angle` to `top`; the 3D pane looks down at
   the studs and the LDView pane shows the same face. Then `front`, then
   `right`. If 3D and LDView disagree on which face is which, the longitude
   sign in `orbit.ts` is inverted — fix `orbitFromAngle`/`angleFromOrbit`
   together and re-run their round-trip test.
3. **Orbiting drives everything.** Drag the 3D view; on release, `--angle` in
   the control panel changes, both engine panes re-render, and the LDView pane
   fetches one new frame — not one per pointer move. Watch the server log:
   one LDView invocation per release.
4. **A missing LDView is legible.** Temporarily rename `vendor/LDView.app` and
   confirm the reference pane reads "LDView is not installed — run
   scripts/setup-ldview.sh" rather than going blank. Rename it back.

- [ ] **Step 4: Stop the servers**

Run: `kill %1`; Ctrl-C the Vite server.

- [ ] **Step 5: Commit any fix the walkthrough forced**

If step 3 turned up a sign error, the fix belongs in `orbit.ts` with the test
that pins it — add the failing assertion first.

---

## Self-review notes

**Spec coverage.** LDView on demand at the settled lat/long (Tasks 1, 2, 4);
three.js `LDrawLoader` over the `/ldraw` mount with orbit in the view (Task 5);
orbit sets `--angle` for every other pane (Tasks 3, 6); both panes labeled for
what they are (already in `sources.ts`).

**What cannot be unit-tested here, and why that is stated rather than hidden.**
jsdom has no WebGL, so `ThreePane` has no test — which is exactly why Task 3
extracts every piece of arithmetic it depends on into a module that does, and
why Task 7's walkthrough names the two specific ways the result can be silently
wrong. A green suite on this plan does not mean the 3D pane is correct.

**Deferred, still.** The engine-mesh source — serving `hlr.flatten`'s own
triangles, type-2 and type-5 lines, BFC winding and analytic coverage — remains
the follow-on the spec records. This plan's `sources.ts` entry for `3d` is the
slot it drops into.
