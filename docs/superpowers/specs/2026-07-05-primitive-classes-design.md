# Primitive class hierarchy — design

**Date:** 2026-07-05
**Status:** approved for planning
**Predecessors:** 2026-06-28-primitive-substitution-design.md,
2026-07-05-booleans-fragments-cones-design.md

## Problem

Analytic primitives are plain dicts ("records"):
`{"kind", "sector", "inner", "R", "t"}`. Per-kind behavior is dispatched with
`rec["kind"]` if/else chains at ~20 sites across `primitives.py`, `hlr.py`,
and `shade.py`: parsing, occluder construction (twice in hlr), drawn ops,
rim logic, fit-point sampling, wall/disc face generation, and the smooth-wall
merge. Each new primitive kind (`tndis`, `cyls`, tori are on the roadmap)
would add a branch to every one of those sites.

Secondary problems the same refactor fixes:

- `inner` is overloaded: ring bore radius (int >= 1), cone top radius (float —
  the synthetic merged cone already stores a non-integer), or a meaningless 0.
- Object identity is load-bearing (`rec_occ` / `own_occ` keyed by `id(rec)`),
  maintained by hand in two hlr maps plus a post-merge patch-up block.
- Projection context is 6–7 loose parameters (`right, up, fwd, s, cx, cy,
  half`) threaded through every geometry signature, plus two closures
  (`to_AB`, `ray_origin`) rebuilt in hlr.

Note: the mesh cache (`repair.py`) stores only triangles — records are never
serialized, so no serialization constraint applies.

## Decisions (made with user)

1. **Clean break** — no dict-compatibility shim, no dispatch registry. All
   call sites and test constructions convert in one pass; the 180-test suite
   is the safety net.
2. **`Projection` value object** — bundles the camera/pixel-fit context.
3. **Smooth-wall merge moves to `primitives.py`** — it is pure record
   geometry and constructs primitives; shade keeps only tone/fill concerns.
4. **Terminology** — "rec" (record) retires. Variables become `prim`; the
   face-dict key `"rec"` is renamed to `"prim"`.

## Design

### Class hierarchy (`primitives.py`)

```python
@dataclass(eq=False)          # identity semantics; hashable by id, like today
class Primitive:
    R: np.ndarray             # 3x3; columns U, A, V (world transform)
    t: np.ndarray             # world origin
    sector: float = 360.0     # degrees
    kind: ClassVar[str]       # keeps face-dict "kind" strings stable
```

Not frozen: `functools.cached_property` (used for `occluder()`) needs a
writable `__dict__`, and frozen would add nothing — `eq=False` already gives
the identity hashing the pipeline relies on.

| Class | Extra field | `occluder()` | `wall_rims()` | `faces(proj)` |
|---|---|---|---|---|
| `Edge` | — | `None` | `[]` | `[]` |
| `Disc` | — | `DiscOccluder(0, 1)` | `[]` | flat disc face |
| `Ring` | `inner: int` | `DiscOccluder(inner, inner+1)` | `[]` | annulus, bore hole when full-sector |
| `Cylinder` | — | `CylinderOccluder` | base + top | wall span faces |
| `Cone` | `top: float` | `ConeOccluder` | base (+ top if `top > 0`) | wall span faces |

`Ring.inner` and `Cone.top` replace the overloaded `inner` key. `Cone.top` is
a float (synthetic merged cones need non-integer values).

### Base-class API

- `occluder() -> Occluder | None` — `cached_property`, so every consumer gets
  the same instance. This deletes hlr's `rec_occ` map, the `own_occ`
  indirection's construction half, and the entire post-merge "build synthetic
  occluders" block (hlr.py:402–415): `face["prim"].occluder()` is always
  correct and lazy. The global stroke-visibility occluder list is still built
  only from the original (unmerged) analytic list, preserving the current
  rule that merged synthetic walls never join it.
- `wall_rims() -> list[tuple[key, side, slope]]` — default `[]`;
  `Cylinder`/`Cone` override with today's `wall_rims(rec)` logic.
- `drawn_with_depth(proj, skip_rims=None) -> list[(op, depth_fn)]` — per-kind
  bodies from today's `drawn_with_depth` dispatch.
- `fit_pts(n=16) -> (N, 3)` — world sample points for the pixel fit; replaces
  `hlr._analytic_circle_pts`.
- `faces(proj) -> list[dict]` — absorbs shade's `faces_from_analytic` per-kind
  bodies plus `_cyl_wall_faces`, `_con_wall_faces`, `_wall_span_face`, and
  `_radius_pts` (which becomes a shared helper method; the per-kind default
  radius rule becomes a small `radius_at(level)` override). Face dicts keep
  their current shape and `"kind"` strings; `"rec"` becomes `"prim"` holding
  the `Primitive` instance.
- `is_full` property — `sector >= 360.0 - 1e-9`, replacing the repeated
  epsilon comparison.

Occluder classes (`CylinderOccluder`, `ConeOccluder`, `DiscOccluder`,
`TriangleOccluder`), `Ellipse`, `project_circle`, and `visible_subops` are
untouched.

### Projection (`primitives.py`)

```python
@dataclass(frozen=True)
class Projection:
    right: np.ndarray; up: np.ndarray; fwd: np.ndarray
    s: float; cx: float; cy: float; half: float

    def to_AB(P) -> (A, B, Z)       # world -> camera plane + depth
    def to_px(P) -> (px, py, z)     # world -> pixel space + depth
    def ray_origin(xs, ys) -> (N,3) # pixel -> world ray origins
```

Lives in `primitives.py` because hlr imports primitives (the reverse would
cycle). hlr constructs it from `view_basis` + `_fit_params` and passes it to
primitive methods; it replaces hlr's `to_AB`/`ray_origin` closures and
shade's `_project_px`. `shade.faces_from_tris`, `order_faces`, and
`cull_occluded_faces` take it too — they already receive `ray_origin` + `fwd`
piecemeal. The faceted pipeline (`_visible_segments_faceted`) builds one as
well so shade has a single signature.

### Construction

- `parse_primitive(name) -> (kind, sector, inner) | None` keeps its exact
  contract (it is a pure name parser with thorough tests, including the
  ndis/cyls/chrd fallback semantics and docstring rationale).
- New `from_ref(name, R, t) -> Primitive | None` maps the parsed tuple to a
  class (`inner` routing to `Ring.inner` / `Cone.top`). `flatten()` calls it;
  `out["analytic"]` becomes a `list[Primitive]`.

### Smooth-wall merge

`shade.merge_smooth_wall_recs` + `shade._merged_wall_rec` move to
`primitives.py` as `merge_smooth_walls(prims) -> list[Primitive]` and a
private constructor helper returning `Cylinder`/`Cone` instances. Logic is
unchanged, including: rim-key union-find, the equal-slope/opposite-side
predicate, kind equality (`type(a) is type(b)`), pass-through of partial
sectors and creases, and the docstring gotchas (see memory:
boundary-merge-findings). `shade.faces_from_analytic(analytic, proj)` becomes
a thin loop: `[f for p in merge_smooth_walls(analytic) for f in p.faces(proj)]`.

### Call-site inventory (what converts)

- `hlr.flatten` — construct via `from_ref` (hlr.py:94–99).
- `hlr._visible_segments_analytic` — occluders from `p.occluder()`; rim
  suppression via `p.wall_rims()` / `p.is_full`; drawn ops via
  `p.drawn_with_depth(proj, skip_rims)`; fit cloud via `p.fit_pts()`;
  `rec_occ`/post-merge block deleted; `own_occ` built from
  `f["prim"].occluder()`.
- `hlr._analytic_circle_pts` — deleted (now `fit_pts`).
- `shade` — `_radius_pts`, `_cyl_wall_faces`, `_con_wall_faces`,
  `_wall_span_face`, `faces_from_analytic` bodies, merge functions all move
  or shrink as above. `cull_occluded_faces`' `f.get("kind")` check is a FACE
  kind (`"tri"` etc.) and stays as-is.
- `primitives.wall_rims`, `drawn_with_depth`, `drawn_curves` — become
  methods; module-level functions removed (clean break).
- Tests — ~34 literal dict constructions become constructor calls;
  `rec["kind"]` assertions become `isinstance` / `.kind`.

### Out of scope / non-goals

- No new primitive kinds. This refactor only makes `tndis`, `cyls`, and tori
  cheap to add later (one new subclass each, zero edits at consumer sites).
- Face dicts stay dicts (a future pass may class-ify them if warranted).
- No behavior change of any kind: geometry, sampling counts, epsilons,
  suppression predicates, and SVG output are bit-for-bit preserved.
- `ndis` stays faceted (see `parse_primitive` docstring); the alias table and
  fallback path are untouched.

## Testing / acceptance

1. Full suite green (180 tests), with test constructions converted
   mechanically — no test semantics change.
2. Specimen regression: render the specimens list before and after; SVG
   outputs must be byte-identical. Any diff is a refactor bug, not a
   judgment call.

## Risks

- **`cached_property` + dataclass:** requires non-frozen; `eq=False` keeps
  default (identity) `__hash__`. Verified pattern; a unit test should assert
  `p.occluder() is p.occluder()`.
- **Merge predicate type check:** `type(a) is not type(b)` must replace the
  kind-string comparison; a subclass-vs-subclass `isinstance` would wrongly
  merge a Cylinder with a Cone if one ever subclasses the other (they don't,
  but `type is` encodes the intent).
- **Hidden dict assumptions:** any `.get(...)`/`in` probing of recs missed by
  the inventory will fail loudly (AttributeError/TypeError), which the suite
  and specimen diff will catch.
