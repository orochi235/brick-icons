# Turning a part to face the camera

**Built and on by default.** A part is drawn under the turn its own `.dat`
declares. Read this before proposing that we work out a turn for the parts that
declare none — that was measured and it does not work.

## What it does

394 parts in the library carry a `!PREVIEW` meta, which is LDraw saying the
default view shows the wrong side of this part. `library.declared_pose` reads
it and the render goes through under that rotation. Everything else is
untouched: 24,197 parts declare nothing and draw exactly as before.

The turn goes in as the geometry's root basis, not as a camera move, because
`hlr.view_basis` derives its up vector from world Y and so cannot express the
roll a turn about X or Z asks for. LDView is handed a file rather than a basis,
so `render.posed_wrapper` writes a one-line `.ldr` that instantiates the part
under the same matrix. `--no-pose` draws a part as authored, and a posed render
stamps `posed` in its label.

Every declaration is a quarter turn — a signed permutation matrix with
determinant 1 — which is the rule Mike set. A reflection is refused rather than
folded in: it would flip the winding of every face and render the part
inside-out with nothing reporting an error.

| declared turn | parts |
|---|---|
| 180 about Y | 357 |
| 180 about X | 23 |
| 180 about Z | 8 |
| plus or minus 90 about Y | 3 each |

## Working out a turn for the other 12,113: measured, and no

The tempting next step is to turn the parts that declare nothing — find where a
part's decoration sits and rotate whichever quarter turn puts it toward the
camera. `scripts/assess-pose-inference.py` scores that against the parts that
do declare, which is a free oracle: a rule worth having has to reproduce the
library's own answer.

It does not come close. Three objectives, over the 351 declaring parts that
carry decoration at all:

| rule | agrees with LDraw |
|---|---|
| squarest of all 24 quarter turns | 4 (1.1%) |
| squarest of the 8 that keep the part upright | 32 (9.1%) |
| smallest turn that brings the decoration round | 3 (0.9%) |
| **guessing "180 about Y" without looking at the part** | **320 (91.2%)** |

Reading the part is nine times worse than not reading it. The reason is in the
population rather than in the objective: **77 of the 394 are not printed at
all**, and 43 carry no decoration geometry for such a rule to look at — plain
`11203 Tile 2 x 2 Inverted` among them. A `!PREVIEW` is a statement about how
the moulding was authored, not about where a decal sits, so a
decoration-facing rule is answering a different question from the one the
library answers.

The blast radius says the same thing from the other side. On a 1,000-part
sample of the 12,113 undeclared printed parts, the best of those rules turns
26.9% of them (±2.8 points) — roughly 3,250 renders changed, by a rule that is
right one time in eleven wherever it can be checked.

## The part that started this is a different problem

`14769ptk`, whose "K" goes flat, declares no turn — and the rule above leaves it
alone anyway, correctly: its decoration already faces the camera at +0.500. The
K is unreadable because iso at latitude 30 *shears* a glyph lying flat in XZ,
not because the glyph faces away. Turning the part toward the camera and making
a flat glyph legible are two different asks, and the 394 declarations are
evidence for neither.

The measurement in the earlier baton stands: iso plus 90 in latitude, `120,45`,
makes the K legible while the tile keeps its rim. Nothing decides yet which
parts should get that, and the oracle used above cannot settle it.

`87544dq0`, the other part in that pair, needs nothing further — it declares
180 about Y, and honoring the declaration is what fixes it.
