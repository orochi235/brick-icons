# Design: Mesh-repair pass (winding) + analytic HSR — closing the flat3 base slivers

Status: proposed (2026-07-04). Builds on
`2026-06-28-primitive-substitution-design.md` (analytic occlusion oracle) and the
`flat3` shading work now on `feat/scaled-svg-library-shading`.

## Why

`--shade-style flat3` renders bright slivers at the base of hollow parts. Root-cause
analysis (this session) shows they are **two distinct bugs**, not one:

1. **Winding (3001, 3020).** `flatten` (hlr.py:36–73) parses **no LDraw BFC** — no
   `CERTIFY`, no `INVERTNEXT`, no transform-determinant tracking. Raw type-3/4 vertex
   order goes straight into `out["tri"]`. Because winding is therefore untrustworthy,
   `shade.faces_from_tris` compensates by **flipping every back-facing tri to face the
   camera** (hlr `nv[2] > 0` branch). On 3941, 280 of 384 tris get flipped; a hollow
   part's underside frame flips "up" into the bright top tone and leaks at the front-
   bottom edge past the painter sort. This is genuinely a winding bug.

2. **Hidden-surface removal (3941).** With tri-fills suppressed, 3941's base patches
   persist — they are **analytic** interior tubes/rings correctly facing the camera
   that the outer wall should occlude. Winding repair does nothing here. `shade.
   faces_from_analytic` does no depth culling, so interior analytic surfaces near the
   base leak below the outer wall.

A provisional depth-HSR cull for tri faces (added this session, uncommitted) already
closes 3001/3020. It confirms the mechanism but is a band-aid over the flip hack. This
design replaces the hack at its root and closes the analytic class too. Both components
ship as **one body of work**.

## Component 1 — Mesh-repair pass (winding)

A new module `brick_icons/repair.py`. It produces, per part, a triangle list with
**correct outward-facing orientation**, computed once and cached to disk. Repair is
**view-independent** (winding is a property of geometry, not camera), which is what
makes caching sound.

Accuracy is favored over speed (per owner). Two-tier method:

- **Primary — honor LDraw BFC.** Extend `flatten` to track BFC state through the
  recursion, per the LDraw BFC spec:
  - `0 BFC CERTIFY CCW|CW` (CCW is the default winding); `0 BFC INVERTNEXT` inverts the
    next type-1 subfile reference; `0 BFC CW`/`CCW` mid-file switches local winding.
  - Accumulate a boolean **invert** flag = XOR of (each level's `INVERTNEXT`) and
    (sign of `det(M)` < 0 for each type-1 transform — a mirrored subpart flips winding).
  - Emit each triangle with a normal oriented per the effective (CCW/CW + invert) sense
    so it points **outward**. Certified parts (the bulk of the official library) become
    authoritative.
- **Fallback — ray-cast outside test.** For triangles from **uncertified** subfiles
  (no `CERTIFY`), determine outward direction geometrically: shoot a ray from the tri
  centroid along its normal and count intersections with the full mesh using the
  existing occluder oracle (`primitives.TriangleOccluder`). Odd crossings ⇒ the normal
  points inward ⇒ flip. Robust on the closed-shell parts we render.

Certification is tracked per-subfile during flatten, so a part can mix certified and
uncertified sources and each triangle uses the right tier.

### Cache

- Location: **in-repo `.cache/mesh/` (gitignored)**. Add `.cache/` to `.gitignore`.
- Key: `<part-id>-<hash>.npz`, where `<hash>` is a stable hash over the **fully resolved
  input** — the top `.dat` plus every subfile `flatten` reads (content hashes), so any
  edit to the part or its includes invalidates the entry. The LDraw library is static in
  practice, but hashing includes is cheap insurance.
- Payload: the oriented triangle array (`float32 (N,3,3)`) and a schema/version int so a
  format change invalidates old entries. Analytic records are unaffected (they carry
  their own axis/normal and are not part of the repaired-tri cache).
- Miss → compute (flatten + BFC + ray-cast fallback) → write. Hit → load array.

### Consumer change

`shade.faces_from_tris` **drops the flip hack**: with trustworthy outward normals it
**culls true back-faces** (outward normal points away from camera) and tones by the real
outward normal. No more flip-to-camera. Tri toning (top/left/right) is then correct by
construction rather than by lucky winding.

## Component 2 — Analytic HSR (3941 base patches)

Extend the depth-HSR cull to analytic faces, fixing the self-culling bug found this
session: a curved face's stored `depth` is a **band mean**, not its surface depth at the
centroid pixel, so a naive centroid test makes the outer wall cull itself (observed:
10/13 cylinders wrongly culled).

Fix: cull a face when another occluder is nearer than the face's **own-occluder depth at
its centroid** (self-depth), not nearer than its stored mean depth. Each analytic face is
linked to the occluder built from the same record, so self-depth is the true near surface
of *this* face at that pixel. Concretely:

- For a tri face, self-depth = centroid depth = mean vertex depth (exact; planar).
- For an analytic face, self-depth = `own_occluder.depth(centroid_ray)`.
- Cull if `min(other_occluder.depth) < self_depth − eps`. `eps` = existing
  `1e-3 * zrange`; the `− eps` margin preserves the coplanar/self exclusion (a face's own
  surface and studs/tops sitting ON its plane must not cull it).

The depth-HSR cull is **permanent** in the pipeline: winding repair removes back-faces,
but only HSR removes *occluded front-faces* (interior tubes, bore walls) that are wound
correctly yet hidden.

## Data flow

```
part.dat ──flatten(+BFC state)──▶ raw tris + certify flags
                                        │
                        repair.repaired_tris(part)   ◀── .cache/mesh/<id>-<hash>.npz
                        (BFC orient; ray-cast fallback for uncertified)
                                        │
                                oriented tris (outward normals)
                                        │
   analytic records ──┐                 ▼
                      ├──▶ faces_from_tris (cull back-faces, tone by normal)
                      └──▶ faces_from_analytic
                                        │
                    cull_occluded_faces (self-depth vs occluders)  ── tris + analytic
                                        │
                              fill_ops (painter sort) ──▶ SVG
```

## Components / boundaries

- `repair.py`: `repaired_tris(part, roots) -> np.ndarray (N,3,3)`. Owns BFC orientation,
  ray-cast fallback, and the disk cache. Depends on `flatten` output + `TriangleOccluder`.
  Testable in isolation: feed a part, assert outward normals on a known specimen.
- `flatten` (hlr.py): gains BFC meta parsing + per-subfile certify/invert tracking. Emits
  raw tris **plus** a parallel per-tri record carrying `(certified: bool, oriented_winding)`
  so `repair` knows which tier to apply and, for certified tris, can orient directly
  without ray-casting. Uncertified tris (`certified=False`) fall to the ray-cast tier.
- `shade.faces_from_tris`: back-face cull, no flip.
- `shade.cull_occluded_faces`: gains self-depth-at-centroid; applies to tris + analytic.
  Needs face→own-occluder linkage passed from `hlr._visible_segments_analytic`.

## Testing

- **Unit (repair):** on a BFC-certified solid (e.g. 3005), every repaired tri normal
  points away from the part centroid (outward). On a hollow part (3001), the underside
  frame normals point **down/inward-consistent**, not up.
- **Unit (BFC):** a subfile referenced with a negative-determinant matrix has its winding
  compensated (mirrored stud orients outward).
- **Unit (HSR self-depth):** the outer cylinder wall of 3941 is **not** culled;
  interior tube faces below the outer wall **are** culled.
- **Cache:** second call for the same part loads from `.cache/` (no recompute); editing
  the part file changes the hash and forces recompute.
- **Visual regression (specimens.txt):** 3001/3020/3941 base slivers gone; the good
  specimens (6143, 4589, 3960, 50950, gears) unchanged. Renders shown inline (per
  [[always-show-renderings]]).

## Out of scope / YAGNI

- No general mesh healing (T-junction welding, hole filling, degenerate removal) beyond
  what winding orientation needs.
- No cache eviction policy — the LDraw library is static; a stale `.cache/` is cleared by
  deleting the dir.
- No change to the analytic outline HLR path, which is already correct.
