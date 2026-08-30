# brick-icons

Renders LDraw parts as line-drawing icons. Two engines behind `--engine`:
`naive` (z-buffer, the reference) and `occt` (OpenCASCADE hidden-line removal).

## LDraw parts are defective, and the engine must not care

Library geometry is cracked, unwelded and inconsistently wound as a matter of
course — that is what `repair.py` exists for. **A rule that assumes a sound
shape is wrong by construction**, and will pass on the parts you tested and
fail on the next defect you have not met. Tried and failed: G1 continuity
tagging (needs two faces per edge), treating a curved free boundary as a rim
(reads a crack as a feature), "both adjacent faces are curved" (assumes a wall
is one surface).

What works asks only whether something was **declared** — type-2 lines, `edge`
primitives, type-5 conditional lines, junctions between exact surfaces. A crack
declares nothing, so it contributes nothing. Hence: don't invest in closing
cracks, invest in rules that survive them. Parts render correctly today with
more than half their edges unpaired.

Never infer geometry from a dihedral angle across *tessellation* — that draws
every facet boundary, the failure the OCCT engine exists to avoid. Between two
exact analytic surfaces it is measurable and safe; measure first
(`scripts/measure-crease-angles.py`).

## Part numbering, and what it does and does not tell you

Counts are from the vendored library, 24,591 part files.

| form | count | meaning |
|---|---|---|
| `3001` | 7541 | base part |
| `3068b` | 3268 | mould variant — **or** a sticker-sheet item (2379 of these) |
| `3068bp00`, `14769p0a` | 8639 | printed (8176 described `Pattern`) |
| `3069bpr0001` | 20 | printed, newer convention |
| `...c01` | 2033 | composite/assembly |
| `...d01` | 899 | sticker (863 of them) |
| `u9…` | 1164 | unofficial |

**Identify printed parts by the description line** (`Pattern`/`Sticker` in line
1 of the `.dat`), not the id: `^\d{3,}p\d+$` catches 3254 of 13081, a plain
letter suffix is ambiguous, and 132 bare-numeric ids are patterned. The id is
fine as a fast path, never as the authority.

**Strip a printed part's decoration and you should be left with its base part** —
`4740p03` → `4740`, and the base exists for 8615 of 8639. That is a free oracle
for the decal-stripping stage over thousands of parts with nothing to label.

## Test on unprinted parts

Printed parts are out of the engine loop until the decal work is picked up;
decoration fails for its own reasons and drags debugging onto the wrong
problem. A fix motivated only by a printed part is not yet motivated.

## Look at renders; never describe them from memory

- **A small pixel diff is not agreement.** Antialias fringe scatters into
  hundreds of tiny components; a real defect is a handful of chunky ones.
  Component-count the diff instead of eyeballing a thumbnail.
- **A silent `[]` is not "unrepresentable".** `occt_faces` returns `[]` both for
  "no exact surface exists" and "my tolerance was too tight", and two tolerance
  constants once deleted whole walls with no error anywhere. Remove the
  `except` and look before believing it.
