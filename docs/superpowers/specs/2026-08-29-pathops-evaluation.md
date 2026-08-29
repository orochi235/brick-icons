# skia-pathops for the 2-D booleans — evaluation

For whoever writes the OCCT adoption design. Assumes you know `geom2d.py`,
its arc recovery (`arc_candidates` / `_ring_d` / `path_d`), and why it exists:
GEOS flattens every curve, so circles have to be refitted out of the boolean
output afterwards. This answers whether Skia's path booleans remove that step.

Measured against `skia-pathops` 0.9.2 (import name `pathops`), the standalone
wheel, on macOS/arm64.

## Verdict

**Adopt it, but inside the OCCT port — it is downstream of the engine swap,
not a prerequisite.** It deletes `geom2d`'s arc recovery only once something
upstream supplies true circles, which is exactly what OCCT is for. It does
not replace shapely.

## Conics survive the booleans exactly

Union of two r=10 circles at d=12, built from conics, comes back as 8 `CONIC`
verbs and no lines, area 538.85970 against an exact 538.85949 — 4e-7 relative.
Skia splits the arcs at the intersection points and re-derives the correct
sub-arc weights (0.948683 for the partial quarters, 0.707107 for the intact
ones). Half-disc and annulus behave the same way.

float32 is not a limit at canvas scale: an r=120 circle measures to 6.6e-7
relative, well under `geom2d.GRID` of 1e-3 px.

## But it never invents curves, which fixes the ordering

The same union built from LDraw-style tessellated circles returns 24 `LINE`
verbs, zero conics, and 2.1% area error at n=16 (0.24% at n=48). Polygons in,
polygons out.

Today every polygon reaching the booleans is already flattened by facet
tessellation, so adopting pathops on `main` as it stands buys nothing and
still costs a dependency. The conic path only opens when the geometry carries
real circles — the OCCT seam. Sequence it accordingly: port the engine, then
swap the booleans, then delete the arc recovery.

## It does not replace shapely

There is no polygon offset in pathops — only `stroke()`. `geom2d.opened()`
(8 call sites in `shade.py`), `close_slivers()` and `buffer_d()` all need
buffer with mitre joins in both directions. Shapely stays for those; pathops
would cover the boolean ops only.

Robustness is not a reason to switch either. Bowties, zero-area spikes,
duplicate vertices, 1e-9 slivers and 1e7 coordinate ranges all come back clean
from both kernels — consistent with `4740p03` no longer throwing.

## Traps — the binding is font-shaped

TrueType has no conics, so every FontTools-flavored layer in this wheel is
quad/cubic only and fails on the one verb that matters here.

- **`Path.conicTo(x1, y1, x2, y2, w)` silently overwrites `y1` with `y2`.**
  Use `Path.add(PathVerb.CONIC, (x1, y1), (x2, y2), w)`, which stores
  correctly. The corruption produces a closed, plausible, wrong shape — a
  "circle" built with `conicTo` measures 257.08 against 314.16 and nothing
  raises. Verify any conic construction by area before trusting a boolean.
- **`op()` and `simplify()` raise `UnsupportedVerbError: CONIC` at their
  defaults.** Both `fix_winding=True` and `keep_starting_points=True` route
  through the pen layer. Pass `False` for both, which means owning winding
  yourself; output arrives as `fillType=kEvenOdd`.
- **`.segments`, `.draw(pen)` and `.area` all raise on `CONIC`.** To measure a
  conic path, copy it and `convertConicsToQuads(tol)` first.
- **No accessor returns conic weights.** `.points` gives coordinates only.
  The only lossless route out is capturing fd 1 across `dump(as_hex=True)` and
  decoding the `bits2float(0x...)` tokens. It round-trips exactly, but it is
  stdout scraping in the path that emits every SVG arc.

That last one is the real integration cost. If it proves unacceptable, the
open alternative is `skia-python`, which wraps more of Skia and may expose
weights directly; it was not evaluated.
