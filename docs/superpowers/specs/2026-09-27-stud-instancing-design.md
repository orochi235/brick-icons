# Stud instancing

**Status: built behind `--stud-instancing` (default `off`) -- see
`brick_icons/instancing.py`.** Two differences from the text below. A cut
stud's clip is taken from the occluding primitive's outline or the coplanar
triangles the samples hit, before the engine runs, not from the engine's
fitted face polygons -- classification has to precede the engine. And a stud
hit by a triangle with a type-5 line on an edge falls back: those are facets
of a curved surface.

For whoever implements or reviews the change: how a render stops drawing each
stud through the engine and places one pre-drawn stud per position instead.

## Why

Measured over the census's 686 core-hours of occt renders, the fill step
(`shade.fill_ops`) is 59% of the time and OCCT's hidden-line removal 0.4%. A
studded part pays for every stud's walls, rims and fills one by one: a
baseplate spends minutes on 1,024 identical studs. The view is orthographic, so
every stud of one type and orientation is the same drawing moved. Drawing it
once also makes every stud identical by construction -- 51542's studs lost
their wall fills (defect `51542-stud-walls-unfilled`) because each stud went
through the fill step separately.

## What changes

`--stud-instancing off|all`, default `off` until vetted.

### 1. Studs stay occluders, stop being drawn

A declared stud (geometry under a `p/stud*.dat` reference that `hlr.is_stud`
accepts) stays in the engine's input, so everything behind it is still hidden
exactly as today. What it stops contributing is output: no stud edges are
selected as drawn loci, and no stud faces reach `shade.fill_ops`. Both engines
already know which primitives are studs (`Primitive.stud`); `flatten` extends
the same tag to the type-2, type-5 and triangle lines under a stud, so
`stud10`'s authored chords and `stud-logo`'s faces are withheld too.

### 2. Classify each stud before the engine runs

For every stud instance, sample points on its rims and top face and test them
against the non-stud geometry with the naive engine's occluder index
(`primitives.OccluderIndex`):

| samples | stud is | drawn as |
|---|---|---|
| none occluded | clear | `<use>` |
| all occluded | hidden | nothing |
| some occluded, every hit on a planar face | cut | `<use>` clipped by those faces |
| some occluded, any hit on a curved or ambiguous occluder | fallback | the engine, as today |

A fallback stud is decided before the engine runs, so it simply keeps its
drawing role. Each render records its clear / cut / hidden / fallback counts in
the census `counts` dict, so the fallback rate is measured, not assumed.

A cut stud's clip is its footprint minus the screen outline of the planar
faces the samples hit, taken from the engine's own fitted face polygons.

### 3. One definition per stud type, orientation and color

Keyed on (stud file, rotation matrix rounded, color). Drawn by running that
lone stud through the same engine, same view, at the part's px-per-LDU, with
the stud stroke tier (`process.stud_weight`) as its line weight. The result is
strokes and fills about the stud's projected origin -- one set of ops that both
writers consume:

- SVG: emitted once under `<defs>` as two groups, the stud's fills and its
  strokes, each placed with `<use x= y=>` (a cut stud's pair shares one
  `clip-path`). Kept apart so a stud whose shading must differ -- nothing
  varies per stud today, but a cast shadow would -- can keep its lines and
  swap only its fill.
- PNG (gray, mono): the definition's strokes translated to each position and
  clipped by the same polygon. No second drawing of a stud exists.

### 4. Paint order

Part fills, then studs, then part strokes. Edges behind a stud never reach the
drawing (step 1); edges in front of a stud draw over it. A stud standing above
the part's outline now draws its own outline at the stud weight instead of
being folded into the silhouette contour -- which closes
`3001-contour-studs-at-line-weight`.

### 5. Where it does not apply

Translucent (`--opacity < 1`) and wireframe renders draw hidden geometry on
purpose; instancing is off for them. `--scale-mode physical` takes the same
path as fit, with its own px-per-LDU.

## Proof

1. Unit: a stud's classification from hand-built occluders (clear, hidden,
   cut by a plane, fallback on a cylinder); the definition cache keys; the PNG
   and SVG writers placing the same ops.
2. The 197-part batch (`scripts/vet-goldens.py --parts`) with `off` as before
   and `all` as after: every moved part reviewed on the sheet, diffs expected
   only as antialias noise plus the outline studs of step 4.
3. Timing against `off` on the same node, the two runs interleaved part by
   part (a sequential A/B measures the node's load, not the code): baseplates
   and a studded mid-size set, reported per part.
4. Fallback rate over the batch, per part.
