# 3D pane viewport registration

For whoever next touches `lab/src/panes/`. It answers: how does the 3D preview
come to sit in the same viewport as the engine panes, and where does the
world→pixel map come from?

Today the 3D pane is the odd one out. The 2D panes share one `Camera`
(`zoom`, `pan`) held on the trial view; the 3D pane opts out
(`followsCamera: false`) and runs a perspective camera at `fov: 35` with its
own `OrbitControls`. The engines project orthographically (`shade.py:70`), so
the preview shows a different projection at a different scale, and nothing
lines up across panes.

## The map already exists

An engine render fixes world→viewBox exactly, as two affines the pipeline
already computes:

```
a, b   = P·right, -(P·up)                     # hlr.project
px     = ((a - cx)·s + half, (b - cy)·s + half)   # primitives.Projection.to_px
viewBox= (px_x·f + ox,  px_y·f + oy)          # hlr.fit_affine
```

`right, up, fwd` come from `hlr.view_basis(lat, long)`; `s, cx, cy` from
`hlr._fit_params`; `f, ox, oy` from `hlr.fit_affine(bbox, width, height,
margin, scale)`. Registration is the 3D camera consuming that composition.

## Emit it, don't re-derive it

`process_one` writes `<name>.fit.json` beside the SVG, holding the basis, the
pixel fit, the canvas affine and the viewBox size. It is an artifact like any
other, so the lab reads it through `/api/artifact/{key}/{name}` — no new
endpoint. A Python test pins it: the emitted affine applied to a known world
point equals the coordinate the engine drew.

The alternative — porting `view_basis` / `_fit_params` / `fit_affine` into
TypeScript — puts the projection rule in two places, and the lab's standing
rule is that it derives from the CLI rather than forking it.

## viewport.ts

A pure module, tested the way `camera.ts` is. Given the fit, the pane body's
pixel box and the shared `Camera`, it returns an orthographic frustum and a
camera pose reproducing what CSS does to a 2D pane: letterbox the viewBox into
the body (`xMidYMid meet`, as the SVG declares), then `translate(pan)
scale(zoom)` about origin `0,0`.

Tests: a world point at the fit's center lands at the pane's center at `HOME`;
the fixed-point rule (the world point under the cursor stays under it across a
zoom) holds.

## The pane follows

`paneSpec` returns `followsCamera: true` for `'3d'`. `OrbitControls` keeps
rotate and nothing else — `enableZoom={false}`, `enablePan={false}`, rotate on
right and middle drag. Left-drag is the shared pan, wheel is the shared zoom,
and drag-end still writes `--angle`. Nothing remains that could dolly the
camera independently and break the shared scale.

## Projection toggle

A `LAB_ONLY` config key `projection` (`ortho` | `persp`), default `ortho`, with
a button in `PoseBar`. Ortho is the engine's projection and the only one that
registers. Perspective follows the same shared pan/zoom, matched at the part's
center plane, and the pane says it is unregistered — so a mark that fails to
line up is explained rather than mysterious.

## Fallback

Before a render lands there is no fit, so the pane keeps the bounding-sphere
framing it uses today and notes that it is unregistered. Registration follows
the first enabled engine pane in `SOURCE_ORDER`.

## Out of scope

The `reference` pane is LDView with `-AutoCrop=1`; it does not register with
the engine panes today and will not after this. `scale_mode: physical` builds a
content-sized viewBox — the sidecar covers it, since it is written after
whichever branch ran, but the two modes frame differently.
