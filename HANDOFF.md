## Baton, 2026-09-08 evening: decals are mirrored, and one legend class is designed but unbuilt

On `main` in the shared checkout. `3feb3d6`, `6be8830`, `6a38636` are the
legend swatch shape, the ingestion log route and the extensionless page URLs;
committed, unpushed. Other sessions are editing `markShapes.ts`, `badges.ts`
and the paint goldens in this same tree, so stage explicit paths.

### The decal slot is filled, ingested and baked

11,215 parts over three keiei runs, then `index-store-attempts.py` and
`index-slot-renders.py --source decal`, then `bake-thumbs.py --source decal`
(9,894 of 9,894, no UNREADABLE, no MISSING). `renders/decal` and the database
agree at 9,894. Still owed: 38 `TimeoutError`, 23 `ProcessDied` — 8 of those
are artifacts of two jobs being killed rather than real faults. The 2,913
`none` rows are decorated parts the finder drew nothing on, which is the next
paragraph's problem, not a gap in the fill.

**Use the `ingest-renders` skill for this. It already has the bake step** —
§3, "Bake, or the wall stays a round behind". This session hand-rolled the
ingest and stopped after the rows, leaving the wall a round behind until the
bake was run separately.

### Decals came out mirrored — FIXED, and the slot is now stale

A decal binds to a body plane, and `planes_from` builds planes only from
color-16 facets. Artwork covering its face edge to edge leaves that face with
no body facets at all, so no plane is built for it and `bind` matches the face
BEHIND the sheet instead — within `BIND_TOL` on a 0.25 LDU sticker, and
antiparallel, which hands `up_aligned` a mirrored frame. `6041468c` has 0 body
facets on its printed face against 354 decoration facets; `190265d`, which
keeps an unprinted border, has 311 and always read correctly. Nothing to do
with printed-vs-sticker.

`unwrap.reseat_plane` moves the bound carrier onto the plane the decoration
itself lies in, pointing away from the same `inside` centroid `planes_from`
already orients against — so it can only supply an orientation that was
missing, never contradict one that was there.

**80 of the 393 corpus parts (20.4%) were mirrored.** `decal-hashes.txt` is
re-frozen against the fix; before/after sheets for `6041468c/d/k` and a sample
of the 80 are on the wall.

**`renders/decal` is now wrong for those parts and has NOT been re-rendered.**
That is 9,894 parts to refill, re-index and re-bake — a fleet job nobody has
authorized yet.

### A "not applicable" legend class: designed, NOT BUILT

Nothing of this is in the tree. It exists only here.

A twelfth cell state for a part the slot does not apply to — a plain brick on
the decal wall — drawn as a thick dark-gray border, which gives it the slash
for free, since `paint` slashes any cell that has a border.

- **The rule is agreement between two signals**: the part is plain
  (`parts.printed = 0`) and no decal was drawn for it. Measured: 11,508 cells
  qualify, 0 parts disagree today, and 697 decorated parts never attempted
  stay `unknown`, which is correct — they are still owed. Where the two ever
  disagree the tiebreak is manual, in a curated file; it starts empty.
- **Precedence ~12**, just under `currently out of scope` and above every
  problem state: nothing was owed here, so nothing failed.
- It needs a new fact on the cell, so `cells.py` supplies it — the wall cannot
  derive it, and a per-slot rule in the client would be the wrong shape.

Two dead ends already paid for. `state = 'none'` in `attempts` does **not**
mean "nothing to decorate": the decal pass only attempts decorated parts, so
`none` means the finder failed on one. And requiring both signals to speak
explicitly leaves 9,028 plain bricks in `unknown`, which is the thing that
looks wrong on the wall today.

### Also asked for, not started

Wall cells inset their captions and badges by 2px — canvas, not CSS, so it is
`Wall.tsx`'s `cornerPad` and the strip geometry rather than a stylesheet.

## The decal slot draws, and its fill is running

On `main` in the shared checkout. `750815a`, `422d3a0`, `9427d0a` are the
decal sheet, the store fill and the lightbox 3D panel; unpushed. Another
session is working the wall's topbar in the same tree, so stage explicit paths.

Two decisions from conversation that the code does not carry:

**Head-on and flat, not the part seen face-on.** The slot draws only the
decoration, unwrapped off its carriers -- `unwrap.decal_sheet` -- rather than
the part rendered down the print's normal. Stickers, printed parts and
decorated assemblies all go through the one path.

**`MAX_DECALS = 4` stays.** The first six over-cap parts in the library
(10057pm0, 10057pm1, 10066p01-03, 100942p01; nine to eleven panels each) are
one decoration shattered over the facet planes of a sculpted head, hair or
wheel. No panel is a readable picture, the largest included, so unwrapping
five or more onto a sheet would tile shards.

### What is running

`onto jobs` -- task `slot-decal-keiei` on **keiei**, 6 shards over the 11,215
parts the slot still owes. keiei is provisioned now
(`scripts/provision-node.sh`), and its output is byte-identical to this
machine's: same LDraw manifest hash as `external-deps.lock` records, same
sha256 on `3941p01.decal.svg` and `004402cc01.decal.svg`.

The earlier in-place run on orochi drew 1,173 parts before it was killed, and
those are indexed -- `renders/decal/` plus rows, via
`scripts/index-store-attempts.py` for the attempts and
`scripts/index-slot-renders.py --source decal` for the drawings. **Two ingest
steps, not one:** the store pass writes its `renders` rows into each shard's
own scratch db (so four writers do not contend on `corpus.db`), so the logs
and the drawings are taken up separately.

**Both launches were clamped to a 30-minute deadline** despite `--timeout 4h`
-- the agent's `-max-job-time` default, which a reinstall reverts. Relaunching
under the same task name continues the run, because `batch.Runner` skips what
its JSONL already holds. keiei's shard lists live in its own tree
(`out/slot-decal/keiei-*.txt`) and travel with `scp`, not with the sync.

**A node's `vendor/` survives `onto sync`, but its job output does not.**
The sync resets what the node holds and is not sending, so a re-sync drops
`out/` -- including the `--each` shard lists, which then makes a launch die in
seconds with an empty log.

## Engine parity: the two engines already agree, and a corpus ranking is running

On `main` in the shared checkout. `git log --oneline @{u}..HEAD` for what is
unpushed; several sessions have this directory open, so stage explicit paths.

**The question was whether naive and occt can be made byte-identical. They
cannot, and they do not need to be — they already draw the same picture.** On
ordinary parts they share 99.5% or more of their ink. Where they disagree at
the op level they usually agree on page: same op count, same sil/edge split,
same arc/line split, different cut points along the same strokes, identical
pixels. An SVG-text or op-list diff reports those as disagreements nobody can
see, which is why the on-page measure is the one that matters.

Three decisions from conversation that are not derivable from the code:

**Rank by chunky component count, never by shared-ink share.** Shared ink is
area-weighted. Of four known open occt defects, three score 87–96% and would
sort below cosmetic differences on smaller parts; 4913's filed defect is two
small arcs, 4.1% of ink. `engine-diff-census.py` reports both, and `chunks` is
the column to sort on.

**naive is not ground truth.** 9258 came out of a random sample drawing a 2x2
plate with no studs at all, against occt drawing all four — naive-only 0.0%,
occt-only 49.8%. naive is the byte-locked reference, not the correct answer,
so a low score is not evidence against occt and the two directions must stay
separate.

**The `white-*` census slots cannot be reused for this.** They are filled
renders — 534 black and 302 white fills on the one sampled — so solid area
swamps stroke differences. The pairs have to be re-rendered at
`--shading outline`, which is what the running job does.

### What is running

`onto jobs` — task `engine-diff-outline` on msb-uai, 96 shards over the whole
library, `--from-library` so the shard set does not depend on that node's
corpus.db (which is an older copy than this one). Rows stream to
`out/enginediff/` via `onto fetch --stream engine-diff-outline`; a killed
shard resumes because `batch.Runner` buries what it cannot finish.

Two things about that node. **resvg is not on any fleet node's agent PATH** —
0.47.0 was copied into `~/.config/onto/work/brick-icons/.venv/bin/resvg` on
msb-uai, gitignored so it survives syncs, and the job passes `--resvg`
explicitly; a node without it fails every part in a second looking like a
render error. And **onto sized the pool to 1 worker off a 16.5G memory
estimate** the job does not come close to using; it was widened with
`onto workers`. Check the width before trusting an ETA.

`shards.txt` at the tree root on msb-uai is scaffolding written over ssh, not
a repo file — `--each` reads its list from the tree, and the next sync removes
it. Recreate with `seq 0 95 > shards.txt` on the node.

### Open

`tests/goldens/defects.toml` is uncommitted and carries two of this session's
edits alongside a peer's: evidence on `3941-top-features-unfilled` that both
missing features are absent as *strokes* under plain outline, so "unfilled" in
its title understates it; and a corrected scope on `35485-ring-is-broken`.

That correction matters for planning. The note said 101 oblique cones; it is
**1,493 across 344 parts**, plus 354 more cones dropped for an elliptical
cross-section that the oblique fix does not address. The 101 came from ranking
by `skew-deg`, which is a per-part max whose axis column is unread for rings,
discs and edges — so its top is junk axis columns `frame` already absorbs, and
35485 itself ranks 5,923rd. `scripts/measure-cone-drops.py` re-derives it.

The fix itself is unbuilt and needs a call: recognize a degree-1-in-v BSpline
whose boundary curves are parallel circles, or carry the primitive's own
description alongside the face. The second generalizes — `_curved_frame`
reading the surface instead of a record of what built it is the root of the
whole class. `brick_icons/occt.py` is a peer's active surface; coordinate
before editing it.

## The shading thread: three fixes, one regression caught, one lead open

`22453b4` `_absorb_dome_walls` closed the 3626cp7d head band on occt; `d46962e`
carries its `_inside_ramp` guard (a peer's commit swept my working-tree change
in) and `23ae627` the tests. `5ee73ca` packs the `--debug-colors cycle` palette
to 48 separable colors, regenerated by `scripts/gen-debug-palette.py`.

**Do not re-land the dome absorb without the extent guard.** Lending a wall a
dome's radial ramp is only safe when the ramp REACHES it: 2947bc01's shaft
carries 12 facets of a dome 6.9 gradient radii away, and SVG clamps outside the
ellipse, so the shaft painted flat dark with the ellipse's own edge crossing it
as a ghost of the ring behind. Dropping the group merge does not fix that --
the ramp itself is the damage.

**The witness bug is fixed** (`513f5ea`), and the shape of it generalizes:
`_bbox_pairs` and `_overlap_witness` both carried a 0.5 px floor and they GATE
EACH OTHER, so relaxing the inner one alone leaves every render byte-identical
-- which is what sent me to the outer one. A pair under the floor got no
ordering constraint at all rather than a weak one. Tubes hit this
systematically: a cylinder behind a facet dome meets each facet in a band a
fraction of a pixel tall. Cost is 2-3x on `order_faces` for the worst parts;
if that ever bites, the lever is a cheaper witness for thin overlaps, not the
floor coming back.

**Still open on this thread, in order.** `2310`'s stud borehole and `59443`'s
extra back chord / missing front rim are byte-identical across that fix, so
they are a different cause and undiagnosed. `3626cp7d-floating-ink-diamond` and
`3626cp7d-lips-lose-a-facet` are filed with reproductions and untouched. Mike
asked about a thumbnail status color update that belongs to no commit in
`lab/` -- the handoff names a session "Status icon for thumbnails" holding
uncommitted `paint.ts` / `Wall.tsx` / `params.ts`; find out whether that
survived.

**`tests/goldens/defects.toml`: two sessions' notes disagree.** The section
below says never stage it; the section I inherited said committing it is fine
so long as nothing is reverted. I committed it twice (`aaf34d8`, `f26a93a`,
explicit paths, nothing reverted) before reading the other note. Worth Mike
settling.

## Working through the open occt defect rows: what landed, and what each probe settled

On `main`, in the shared checkout -- five other sessions had this exact
directory open when this was written, so **stage explicit paths and never
`git add -A`**, and confirm the branch before assuming it. `git log --oneline
@{u}..HEAD` for what is unpushed.

Four fixes are committed: `bd537b1`, `c95e2c9`, `99a9693` and `d46962e` (which
narrows `c95e2c9`), each carrying its own measurements. **`tests/goldens/
defects.toml` holds a note per row and is deliberately uncommitted** -- it is
Mike's shared file; never stage it and never revert it. The new row
`92692-knuckle-gradient-crescents` lives only there.

**An oblique cylinder builds now** (`bd537b1`). A cyli whose axis leans out of
its cross-section plane was rejected, and a rejected primitive is a HOLE in the
sewn shape -- so 49492 drew as three disconnected pieces of a shepherd's crook
and 28660's elbow drew stitched across. Both rows are closed. The same
rejection still drops 101 oblique CONES in the 150 highest-skew parts, which is
what `35485-ring-is-broken` is: an oblique cone is a ruled surface whose normal
turns with height, so `_limb_params` does not hold and `_curved_frame` has no
case for it. `scripts/oblique-cohort.py` names the cohort.

**A facet crease lying on a hidden authored line is no longer drawn**
(`c95e2c9`). `select_authored` matches in 2-D, so any tessellation crease
projecting along an authored line's screen path was drawn as that edge. That
was `49612`'s line down the dome (seven creases) and `53119`'s stray lines (77
ops to 34); it also cleans the cheeks and brow on `3626bpsk` (40 ops to 15) and
the hub diagonals on `3649`. It never adds ink. **Cost:** the lines ride the
same HLR pass, which is 1.0-1.1x on most parts, 1.26x on 4019 (471 authored
lines) and 1.59x on 3649. If that ever matters, the prune to look for is which
lines can be confused at all -- not a second HLR pass, which doubles the phase.

**Two corrections from Mike's read of 92692.** The black stub on the ridge in
front of the studs was mine: `c95e2c9` judged EVERY plain segment locus against
the type-2 spans, and a condline locus is one too, so three silhouette pieces
were dropped along that ridge. `d46962e` narrows the mask to type-2 loci, which
is all its evidence ever covered. ~~The stray ink that pass removed from
53119's swirl and 3626bpsk's cheeks came back with it~~ -- **that reading was
wrong, and the condline avenue is closed; don't design a third approach.**
Measured at `bbc6436`, 53119 at iso: HEAD draws 35 elements, the wide mask
leaves 19, and dropping every `sil` locus out of `select_authored` leaves the
same 19. What goes with them is the swirl's DECLARED silhouette -- the top
blob's outline and the overhang curve -- not stray ink. `d46962e` is right.

**53119's remaining stray ink is a rim circle, not a condline.** Two black
dashes on the skirt at (245,311) and (444,311) of the 700 px render survive
both experiments above; they are fragments of an `ell` locus that HLR calls
visible in pieces. `_drop_lines_hlr_hides` cannot reach them -- it takes plain
seg loci only, and its docstring says why the loose-copy trick a line allows
does not carry to a circle coincident with its own cylinder. That is where the
row goes next.

**The knuckle gradients are CLOSED** (`bbc6436`, plus the occt half swept into
`2407e53`). Not coverage: each knuckle is a `4-4cylse`, which no substitution
claims, so it sews as 16 planar facets whose normals run right round the axis
-- and `attach_group_gradients` reads that 2-D spread as a dome. The origin
separates them: a cylinder's normals lie in the ONE plane perpendicular to its
axis, so the uncentered cloud is rank 2 and a dome's is rank 3. s2/s0 measured
over the specimens is 0.0000 on every faceted cylinder against 0.22 on 3960's
dish, so `_relax_facet_cylinders` cuts at 0.05 and re-fits those groups as a
ramp across the tube, reading the camera-facing facets only. Disarming it in
process leaves all 22 specimens byte-identical; only 92692 and 2947bc01 move.

### Settled by probe, so nobody re-derives them

- **The tube rows (`79306-f1`, `14653-f1`) are not hidden-line misses.**
  Per-face renders against naive: naive draws the whole tube as ONE outer-wall
  face, occt splits each cylinder at the limb and the far-end crescent falls to
  the back span plus the far annulus -- both of which a ray there really does
  hit. Their TONE is what reads as a scoop cut out of the tube. Same question
  as `35480-bore-reads-flat`, and it is Mike's to answer.
- **`3626bpsk`'s tab is one pierce seam; `67811`'s notch is none of them.**
  `scripts/pierce-seam-ab.py` drops each kept seam in turn. On 3626bpsk seam 2
  alone draws the tab (5089 px); on 67811 dropping any one of 17 moves at most
  16 px while all-vs-none moves 4905. Four narrowings are now disproven --
  straddling, containment in a real face, distance to the plane's material
  (2.0 LDU on the bad part against 1.99 on the good one), and same-surface
  (every seam on all three parts is cylinder-to-cylinder at one radius and
  axis). The pass has no test left that separates them, which points at
  `order_faces`' single witness rather than at the seam.
- **`39789`'s dark fans are the stud logo, and naive draws them identically.**
  Only the cup-handle loop off each stud rim is occt's; undiagnosed.
- **`3484` and `6589` drop no surface at all** -- every cyli, con, disc and
  ring builds a face, so neither is the 49492 class.

**A third fix landed** (`99a9693`): `sector_face` drew its arcs off a `gp_Ax2`
and computed its two radial ends from `uh` by hand, and under a placement
orthonormal only to three decimals the two frames differ by 6e-5 LDU -- 600x
MakeWire's tolerance, so the wire never closed and 92692's ring sector built no
face. Rare (no part in a random 300), and the second row in this sweep whose
whole symptom was a surface that silently never reached the shape.

**The single witness in `order_faces` is now the biggest named cause.** It owns
`2310` (a stud painted over the slope that hides it, seen per-face), and it is
where the pierce-seam rows point after four narrowings failed. One witness per
screen-overlapping pair cannot order two faces that interleave;
`_refine_order_clips` is the machinery that already knows this, and whether it
reaches these pairs is the question to ask first.

### Where to pick it up

1. **32 occt rows are still open.** `scripts/surface-drop-probe.py <part>` is
   the first question to ask of any "missing wall / shows through" row; it
   takes a second and it answered 49492 outright.
2. **The oblique CONE is the next real surface gap** (35485, plus 101 of them
   in the high-skew cohort). Decide whether a ruled surface can carry a fill
   before building one -- a BSpline through ThruSections would occlude,
   contribute no fill, and trip
   `test_every_corpus_surface_kind_is_one_the_face_producer_handles`.
3. **The stored `renders/occt` slot is stale** for every part these three
   fixes move -- `4107582e` may already be one of them: it renders with its
   inner square at HEAD. Re-render before reading a wall sheet as current.

## Baton, 2026-09-08 afternoon: store ingested, and the snap verdict was wrong

On `main`, in the shared checkout with two peers. `tests/goldens/defects.toml`
is Mike's and stays dirty; never stage it. Fourteen commits are unpushed.

**The corpus wall is current.** Nothing was ever stranded on studio -- its whole
`renders/` tree was already local and both exit-1s were the fetch inheriting the
store job's status. The 704 queued parts with no `.svg` were 654 the renderer
failed on and 56 in batches it never reached; `store-occt-tail` got 43 of those
56. Two `ingest-bake` passes ran. **What is left is 660 timeouts at the 120s
cap, and 294 of them have a clean occt census row at 300s** -- most between 120
and 240 seconds. That is a cap change, not an investigation.

**Two structural zeros on the wall, one fixed.** `error_elsewhere` matched
`source LIKE '<facet>-%'`, so a slot naming no facet -- `occt`, `naive`,
`ldview`, `reference` -- matched its own name plus a hyphen and found nothing;
the occt wall read zero "problem in another slot" while 654 of its parts had
just timed out. It marks 5,400 now. **The other zero is still there:**
`timed out` and `render error` read 0 on `occt` because `measurements` has no
rows with that source at all -- `rebuild` reads `renders/**` and `out/census*/**`
and nothing else, so the store's own failure logs in `out/store/*/` have never
been ingested. The census logs largely cover the same parts (619 of the 661
already carry an occt error row), which is why this has gone unnoticed. **A
peer closed the ingest half in `847a916`; the wall half is still open** -- see
item 3.

**The snap verdict in `OCCT-MIGRATION.md` was wrong twice and is now right.**
First reading: pass 1 is inert on occt. Second: pass 1 deletes edges. Both
wrong. `_snap_rim_crossings` pass 1 rewrites an arc's two angles and nothing
else, so it cannot drop an op -- `24130` draws 218 elements with the snap alone
and 218 with the cull alone, and only both together lose three.
`cull_orphan_runs` is what deletes, and the snap only moves the endpoints that
stop it recognising a junction. That is item 3, and it is a live defect in the
shipped occt path.

**The lesson worth keeping:** an eyeball pass over a full-frame render is not
sensitive enough to catch a missing stroke. Counting `<path>` plus `<line>` is,
costs nothing, and is `scripts/snap-element-delta.py`.

### Open, in the order I would take them

1. **`cull_orphan_runs` deletes real geometry on occt** -- see the item list
   below, which carries the numbers and the disproof.
2. **The wall's hash should carry its whole client state** -- designed, unbuilt,
   `docs/superpowers/specs/2026-09-08-wall-hash-state-design.md`.
3. **CLOSED by a peer while this was being written** (`847a916`): `db.rebuild`
   takes up every log under `out/store` as a run of kind `store` and files one
   row per part in a new `attempts` table -- state, secs and error, keyed by
   run, part and slot. `scripts/index-store-attempts.py` does the same against
   a live database without a rebuild. **What is not yet done is the wall:**
   `timed out` and `render error` still read 0 on `occt` because
   `cells._LATEST_MEASURE` reads `measurements`, not `attempts`.
4. **The 660 timeouts want a 300s cap**, not another fetch.

**One thing needs a person:** the lab API on `127.0.0.1:8792` was started before
today's `cells.py` change and has no `--reload`, so the wall still shows zero
"problem in another slot" until someone restarts it. It is not this session's
process and two peers were live on it.

# Handoff — `main`: the corpus lab, and the OCCT engine

## The head band is closed on both engines

`3626cp7d`'s dark panel is fixed on occt as well as naive (`_absorb_dome_walls`,
`22453b4`). The `3626cp7d-occt-barrel-dark-band` entry in
`tests/goldens/defects.toml` carries the mechanism and corrects two things this
file used to say: the limb-split pieces never disagreed at the limb, and a
side-on cylinder never full-turns by construction -- no occt cylinder is missing
a dome ramp.

## Two decal fixes landed and are pushed

`match a decal's flat carrier by proximity` and `repair a ring before snapping
it to the precision grid` -- see `git log` for both; each commit message
carries its own measurements and blast radius. `BRICK_GOLDENS=full` was green
at the second one, with both seams re-frozen.

**`tests/goldens/defects.toml` is dirty and shared.** It holds work from at
least three concurrent sessions in this one checkout -- two `3626cp7d` entries
of mine plus other sessions' `classes` edits and new rows. Commit it if you
like, but you will carry everyone's; never revert it. This is why every commit
here used `git commit -F - -- <paths>`: a bare `git commit` takes the whole
shared index, which is how a decal fix once landed inside a commit about
`onto`.

**A peer session (`brick-icons-30`) was told the ingest is clear to run.** It
rebuilds `corpus.db` into a temp file and `mv`s it over the live one. Nothing
in the decal or shading work touches that database, but do not open it
expecting stability while that is in flight.


## Baton, 2026-09-08 midday: hands, wall and pinch fixed; three things open

On `main`, in the shared checkout. `git log --oneline @{u}..HEAD` for what is
unpushed; `tests/goldens/defects.toml` is Mike's and stays dirty.

**76382's hands were a tolerance bug, not a hand bug.** `occt.frame` judged a
primitive's axis against `ORTHO_TOL = 1e-4`, but a .dat writes a placement
matrix to three decimals, so a *rotation in a part file is only orthonormal to
about 1e-3* -- 76382 hangs each hand off 0.985/0.696/0.707, whose Gram
off-diagonal is 1.0e-3. Every cylinder in the hand was read as skew, dropped,
and drawn from tessellation instead. Both tolerances are 3e-3 now, which the
measurement puts in an empty gap: no cyli has an axis residual between 2e-3 and
5e-3, no kind is out of round between 1e-3 and 3e-3, and authored skew starts
ten times higher. `scripts/measure-ortho-residuals.py` re-derives both.

**The reproduce that made it quick:** the hand renders correctly at identity and
breaks under any rotation, while moving the CAMERA ten degrees changes nothing.
That pair says the fault is in the transform algebra and not the pose, and it
cost four renders. The grip's cavity is drawn but coarse against LDView's clean
open C, which is what is left of `76382psj-...` in `defects.toml`.

**Chrome's pinch zoom was invisible to the wall.** Measured at page scale 3:
`devicePixelRatio` stays 1 and `innerWidth` stays 1280, while
`visualViewport.scale` reads 3 and `visualViewport.width` reads 427. Three
things now move together, and **any one alone is worthless** -- the mip level
reads off cell x camera x pinch; the canvas backing store is sized off dpr
TIMES the pinch (without it a sharper tile is downsampled straight back into
the same device pixels); and `visibleRange` takes an origin so it covers only
the slice still on screen. The third is not a cost, it is what pays for the
other two: at 3x the visible area is a ninth, so nine times fewer cells each
want nine times the pixels and the totals are conserved.

**The wall's "max update depth" is closed.** `clampView` hands back its argument
when nothing is out of bounds but builds a fresh object the moment it clamps, so
a camera pinned against an edge rewrote state on every pointer event while its
four numbers stood still. `updateCam` compares by value now. **That fix used to
fail two tests** and the reason is worth keeping: the level pick hung off
`[cam]`, so it depended on a same-valued re-fit writing state to run at all. It
keys on the drawn cell size and the viewport instead.

### Open, in the order I would take them

1. **CLOSED. The wall is current; 660 parts of the queue are timeouts.**
   Nothing was stranded on studio -- `onto fetch -dry-run
   studio:brick-icons/renders renders` reports every one of its 9,597 files
   already local, and both exit-1s were the fetch inheriting the store job's
   status. The 704 queued parts with no `.svg` were 654 the renderer failed on
   (651 `TimeoutError` at the 120s cap, 2 `MemoryError`, 1 `RuntimeError`) and
   56 in batches it never reached. `store-occt-tail` rendered those 56: 43
   stored, 9 more timed out, 4 already had renders. Two `ingest-bake` passes
   ran; the occt slot holds 7,931 renders and 1,689 new thumbnails are baked.
   **What is left is the 660 timeouts**, which want a longer per-part cap or a
   faster path, not another fetch.
2. **CLOSED. `snap-ab-occt` finished 177 of 177.** **The verdict is written up** in
   `OCCT-MIGRATION.md` under "The snap passes on occt" and the remaining parts
   can only confirm or overturn it -- read the finished file against it rather
   than starting the analysis again. **The loose thread is answered, and it went
   the other way:** pass 1 is not harmless. `24130`'s 2,053px component is its
   foot ring's whole front arc, and 13 of the 106 parts pass 2 never touches
   come out with fewer drawn elements than they went in with.
   `scripts/snap-element-delta.py` re-derives the list; the section carries it.
   **CLOSED:** the job finished 177 of 177 and the table is the final one.
3. **`cull_orphan_runs` deletes real geometry on occt.** `30124b` draws 68
   elements with the cull disabled and 66 as it ships, and one of the two is a
   **structural crease** -- the fold between two faces, leaving them meeting
   with nothing drawn between them. `33089` loses 7 the same way. No snap is
   involved; this is the shipped path. The cull exists to peel 2654a's
   inner-rim fraying and is reaching past it. **Disproven, do not
   re-propose:** `join_tol=0.75` is a canvas-px literal handed projected LDU
   (about 39 output px at `30124b`'s scale) and is genuinely wrong, but
   scaling it draws 65 against the shipped 66, so it deletes MORE and is not
   the cause; `cap` and `tol` both derive from the drawn extent and are
   scale-free. The crease terminates where its junction partner is sub-stroke,
   which is the docstring's own fray case -- so the anchor test is probably
   right in principle and wrong against occt's geometry. That is where to
   start. Probes are in the scratchpad and are not committed; they monkeypatch
   `hlr.cull_orphan_runs` to identity and render the four corners.
4. **The wall's hash should carry its whole client state**, so a reload keeps
   the camera, the grid selection and the caret rather than just the slot and
   the lightbox. Designed and NOT BUILT --
   `docs/superpowers/specs/2026-09-08-wall-hash-state-design.md`. Mike picked
   the shape: everything in, condensing optional behind a `condenseHash` param
   in `useParams`.
5. **Pass 2's sweep-direction bug is fixable and nobody has said whether to
   fix it.** The refit emits the circumcircle through (pinch1, pinch2, apex)
   the long way round: 23801 goes from a 41.7-degree separator to 288.7. The
   fix is to pick the sweep that keeps the apex BETWEEN the pinch points --
   NOT to tune `SEP_REFIT_MAX_GROWTH`, which does not separate the damaged
   parts from the clean ones. Mike has seen this and not yet called it; pass 2
   is stylization, so fixing the bug still leaves whether the effect is wanted.
6. **Printed and sticker parts want a `decal` slot** holding a 2D extraction of
   the printing (Mike). Not started, not designed, and a peer has uncommitted
   decal-binding work in `brick_icons/shade.py` and `unwrap.py` -- same seam,
   so agree who owns it first.

### Settled this session, so nobody re-opens them

- **A printed part's years are its own.** LDraw calls the Gryffindor 1x1 brick
  `3005pz0` and Rebrickable calls it `3005pr0018`, so every print fell through
  to the plain brick: 1954-2026, 5,144 sets, 77 colors, for a crest made in one
  2018 set in one color. The `.dat`'s `!KEYWORDS` line names both catalogs'
  numbers and `match` takes that ahead of base, sheet and design. `base` fell
  from 4,218 rows to 817; the rest name no catalog number at all.
- **The reference sheet's halves share a scale**, and it takes `--engine`,
  defaulting to occt. Every `-trim` needs `-alpha off` -- resvg writes an alpha
  channel over an opaque background and trim otherwise collapses to 1x1 without
  failing.
- **The reference cannot be sharpened by a flag.** `-CurveQuality` is already
  12, LDView's ceiling, with `-AllowPrimitiveSubstitution=1` set, and 3820 at
  quality 1 against 12 differs by 2.2% of mean pixel value, so it is live. What
  is left is **authored facets**, which substitution cannot reach.
- **The wall keeps `part` and `source` in its hash**, so a refresh no longer
  closes the lightbox. One jsdom location outlives every case in
  `CorpusWall.test.tsx`, so the suite resets the hash between them.
- **`printed` and `composite` are field-is-the-container badges now** -- a 45
  degree halftone screen at 0.62 pitch, and the two trominoes drawn 2.6x so the
  disc is a hole cut through their join. The `brush` mark stays in the set with
  nothing pointing at it; it is what `printed` used to be.

## Baton, 2026-09-08 midday: the wall's tile path is fixed; three things are open

On `main`, in the shared checkout. `git log --oneline @{u}..HEAD` for anything
unpushed; `onto jobs` for what is running.

**The wall bug is closed.** Four symptoms Mike reported -- the reference grid
blank, the cell-size slider not pulling sprites, the SVG rung leaving one cell
drawn, and panning eventually stopping loading altogether -- were three faults
in one path, all landed:

- **The draw was gated on freshness.** A sprite painted only when the sheet's
  sha matched the store's exactly. Re-encoding the reference slot to WebP moved
  every sha at once, so all of its cells fell through to flat fills and the
  wall showed an empty grid with NOTHING saying why. `hasTile` gates the draw
  now, `isStale` only decides whether to fetch a better tile, and `staleCount`
  warns when a slot goes stale wholesale. The `-stale` paint goldens were
  re-frozen; a stale entry and a missing one have parted ways.
- **The loose-tile cap counted cells already in hand**, so a viewport holding
  more than `MAX_IN_FLIGHT` of them starved everything behind -- permanently,
  since the requested set only grows. That was the pan-until-it-stops symptom.
- **`levelFor(128)` returned the vector rung**, so the cell-size slider's own
  maximum skipped the 128px bake. The vector is the fall-through now.
- The sheet URL carried no version while every bake rewrites the atlas in
  place; the server stamps the image's mtime into the manifest.

**The thing that cost the most time, so nobody repeats it:** the cell-size
slider does NOT drive the level. It is `params.cell * cam.scale.x`, and the
wall auto-fits the whole corpus, so the fit cancels the slider -- at cell size
100 the effective cell is 6.64px, below every threshold. Only CAMERA zoom
changes the rung. Reproducing a tile bug by dragging the slider proves
nothing.

Headless: the site is vite on **`[::1]:5178`** (IPv6 only -- `127.0.0.1:5178`
refuses, `localhost` works); the API is FastAPI on `127.0.0.1:8792`. Port 5173
is a different project. HMR leaves stale wall state, so reload fully after an
edit before believing a symptom.

### Open, in the order I would take them

1. **`76382p__`'s minifig hands are still a mess** (Mike, this morning). Not
   looked at at all -- no diagnosis, no defect row.
2. **The four naive-tail rows are measured but undecided.** Both engines
   scanned over 500 random parts with `scripts/measure-snap-gaps.py`:

       engine   move >= 0.5px    pass-2 refits   median move
       occt     177 (35.4%)      53              0.013 px
       naive    201 (40.2%)      59              0.098 px

   So pass 1 is NOT vacuous on occt and the populations are close. What is
   missing is whether occt's moves are REPAIRS -- three on `4019` were checked
   by eye and all three were, but that is one part.
   **`scripts/snap-render-ab.py` timed out over the 177 affected parts and
   wrote nothing**, because it only writes `--results` at the end. Make it
   append per part before re-running it.
3. **studio is baking the occt render slot** (`onto jobs`, task
   `store-occt-studio`, 7,397 unprinted parts). `fetch-occt-studio` streams it
   home. **When it finishes, run `out/ingest-bake.sh` once more** -- the pass
   that ran this morning started while studio was still writing, so its last
   batches are indexed but unbaked. 10,708 printed parts of the gap are still
   unrendered.

### Traps worth keeping

- **`onto fetch <node>:<path> .` FLATTENS.** It dumped 659 SVGs into the repo
  root. Give it the matching directory, never `.`.
- **`onto sync` stages untracked files to build its patch**, so `renders/`
  travels with every sync (`*.svg` there is deliberately not ignored) and once
  put one 111 MiB over its 8 MiB limit. It also ships a peer's uncommitted
  edits to a render node, which is why studio was given unprinted parts only.
- **`onto sync --force` deletes node files the sync is not sending.** Three
  files existed ONLY on studio (`lab/ab.html`, `lab/src/corpus/abBadges.tsx`,
  `abOldBadges.ts`); they are rescued into the working tree, untracked, and
  want committing or deleting by whoever wrote them.
- **`onto` has no dependency primitive** -- it 409s while a tree is locked. Do
  not build a poll-and-submit job for it.
- **Nothing fetches on its own.** `--out`/`--to` only record a destination; a
  `fetch --stream` must be launched and must outlive the job it follows.
- **A crash report from `IntUnifyFaces` is by design** -- `_unify_survives`
  probes UnifySameDomain in a forked child because it segfaults on cracked
  meshes. Exactly 1 part in 500 trips it: `23799`.

## Baton, 2026-09-07 night: naive's tail is audited, half of it landed

On `main`, in the shared checkout. `git log --oneline @{u}..HEAD` for anything
unpushed.

**Do this first: work the rest of naive's post-processing tail.** The audit
that names every row is `OCCT-MIGRATION.md`, section "What naive does that occt
does not" -- read that, not this. Four rows are still open and they are one
cluster:

    _snap_rim_crossings pass 1   snap a partial arc's ends onto the junction
                                 it grazes
    _snap_rim_crossings pass 2   counterbore separator refit -> `refits`
    _refit_candidates            the moved seam as an arc candidate
    _fold_arc_loops              chained fold-arc spans -> `loops`

`hlr.visible_segments` runs all four on the naive branch and none on the occt
branch, so `fill_ops` gets `refits=()` and `loops=()` and their downstream
passes (`shade.refit_fill_boundaries`, the `loops=` sub-region outlines) never
fire. `fold_ells` is built from `fit_ells` inside `_visible_segments_analytic`,
which occt never enters, so `cull_orphan_runs(protect=...)` is vacuous there
too.

**The question is whether they are NEEDED, not how to port them.**
`OCCT-MIGRATION.md` item 4 has said so since the port started and it is still
the right instruction. Pass 1 exists because naive's occlusion is SAMPLED --
`visible_subops(n=64)` stops up to a sample short of the true graze, leaving an
arc end "just next to" the stroke it should touch. occt does real hidden-line
removal and may land the graze exactly; if it does, pass 1 is machinery with no
defect to fix. Establish that with a measurement on a counterbore part before
writing any code. Pass 2 is a different animal -- it is stylization (make the
separator read concentric with the bore), not a repair, so it is a design call
rather than a gap.

**Two traps if you do port any of it.** The engines emit ops in different
spaces: naive in canvas px at `render_px`, occt in projected LDU normalized
later by `fit_segments`. `_snap_rim_crossings`'s `max_snap` is degrees and
carries over; its `vertex_tol=0.25` is op units and does not. And the pass runs
BEFORE `fit_silhouette_arcs` on naive -- match that order rather than inventing
one.

**What landed tonight** -- `git log` for the shas; the audit doc marks each row.

- Decoration authored as an analytic primitive is drawn. It never survived the
  sew: an author partitions a wall into colored and color-16 sectors of the
  same surface, `UnifySameDomain` merges them back (correctly, as geometry),
  and the color is gone. The faces are built from the primitive list instead.
  `unwrap_decoration` also gets naive's two arguments now -- the analytic list
  as carriers, and `ellipses_out`.
- occt's drawn ops go through `dedupe_segments`, with a new occt-only
  `keep_order`. A circle arrived as contiguous spans of itself and each was
  stroked separately.

**Two rows are closed as WRONG, not as done.** Do not re-propose either.
`ink_prims` cannot be ported: its first rule is "color is not 16", and a
printed part whose *body* is authored in a color (`9359`, a green brick with a
white TAXI print) has every structural edge it owns caught by it -- porting it
took the stud rims off `9359`, `80400`, `6141p01`. And
`test_a_fill_boundary_carries_no_sampled_boundary` now skips pure-black fills:
a junction-lens pocket is a difference against the buffered stroke band, so its
boundary is a buffer boundary by construction and counting it measures pocket
gnarliness rather than the defect the test is for. **Mike has not signed off on
that test amendment** -- it is a two-line skip in `tests/test_occt.py` and
reverting it fails the dedupe on `32062` alone.

**Not in scope and still open:** `004490h`'s bottom line of small text draws as
dots and dashes where LDView draws letters. `shade.RESIDUE_CRUMB` set to 0
recovers a few glyph pieces and not the start of the line, so the cull is a
contributor and something upstream fragments the text as well. Its `$` glyphs
came back with the decal arc recovery; the line did not.

**`out/ellip-before/` is untracked and is the only copy of the pre-restage
SVGs.** The originals were overwritten. Do not clean it up. `out/audit-2a/`
holds tonight's A/B sheets and is disposable.

**Four other sessions share this exact working directory** -- `brick-icons-60`,
`brick-icons-4b`, `brick-icons-9d`, `brick-icons-bb` -- and "Status icon for
thumbnails" is in the `.claude/worktrees/defect-sweep` worktree. Stage explicit
paths, never `git add -A` or `git commit -a`, and confirm the branch before
assuming it. `tests/goldens/defects.toml` is Mike's, written by the lab UI, and
is permanently dirty.

## Baton, 2026-09-07 evening: the orthographic reference is a real slot now

**LDView is being replaced, and Mike has said so plainly** -- "it has a
ceremonial place on the board because nobody has the heart to fire it but it is
not fit for purpose". It disagrees with the library three ways and none is
tunable: it renders perspective where our projector is orthographic, so no
pixel comparison means anything; `-CurveQuality` only applies with
`-AllowPrimitiveSubstitution`, so what it draws is not the part's geometry
(4070's "hexagonal recess" was LDView redrawing an r=4 `4-4cyli`); and its
internal color table overrides LDConfig. That is why every finding taken from
it has been structural. It stays on the board for now.

**The replacement is `ortho`, and it bakes.** `fa4c653` gave it a headless
driver -- `scripts/shot-sink.py` serves `lab/dist` beside the library and
launches its own Chrome, so no dev server and no person opening a tab.
`e278a7a` made it a slot: `ortho` is in `db.SOURCES`, renders index at
`renders/ortho/<part>.png`, and the bake is

    .venv/bin/python scripts/shot-sink.py --list <parts> --out renders/ortho

resumable by re-running it. **Its `_CANONICAL` argv is a config key and nothing
runs it** -- the renderer is a browser drawing a whole list in one WebGL
context, and a per-part CLI flag would launch Chrome 24,591 times.

**Two traps it cost to find.** Headless Chrome has no GPU, so WebGL is off
unless SwiftShader is named: `--use-angle=swiftshader` **and**
`--enable-unsafe-swiftshader`, mandatory since Chrome 131. Without them the
page loads and renders nothing, which reads as a broken renderer. And
`shot.html` was not in vite's rollup inputs, so `lab/dist` had no page to
serve; `npm run build` in `lab/` after touching `shot.ts`.

### What is next, in order

1. **Bake the corpus.** Nothing has run past five parts. `--batch` restarts the
   browser per batch so a leak costs one batch; sizing it is unmeasured.
2. **Frame registration, and it is the one that decides whether this is worth
   it.** Mike: "we'll be using it to drive our gradient fill sampling too."
   `shot.ts` fits its own bounding box with a 1.02 pad, so a pixel in the
   reference does NOT map to a point on our face. Sampling needs it to share
   our pixel fit exactly, not approximately.
3. **Shading, explicitly deferred by Mike.** `LDrawLoader.smoothNormals` is at
   its default `true`, so a faceted cylinder shades smooth while our `flat3`
   tones per facet group. The key light is a guess at LDView's `-LightVector`;
   the `0.55` ambient already matches `shade.ramp_b`'s floor exactly.
4. Part color has no override -- the render is whatever colors the part file
   names. Still true, but no longer the magenta bug it looked like; see the
   late baton.

Items 1 and 2 are done: see the late baton at the top. The slot was renamed to
`reference` there, so the migration this section warned about never came due.

## The coplanar sticker measurement is done, and `f832da6` has two regressions

**The coplanar paint-order fix redraws 87% of the sticker class**: 3,884 of
4,454 measured parts move pixels, 4,091 change paint order, median 2,740 px or
6.3% of the frame. 59 parts errored (51 timeouts, 3 GEOS, 5 killed by a
relaunch) and cannot move the answer -- 86.1% to 87.4% whichever way they fall.
`scripts/coplanar-affected.py` (`f130bf8`) is the tool; rows in `out/coplanar/`,
the 59 in `out/coplanar/retry-batches.txt`, already on studio and never run
because a peer took the tree.

**Consequence nobody has acted on: the wall's `silhouette-occt` slot is stale
for about 3,900 stickers**, several stored as blank grey discs that now draw
their artwork.

**`f832da6` fixed 35480 and broke two other parts.** Filed as
`3626bpsk-tab-under-neck-stud` and `67811-notch-through-hub-wall`, both open,
both with the in-process reproduction and both narrowings that are already
disproven. Mike's call was **leave it and file them**, not revert. The sample
was 60 parts: seams kept on 14, pixels move on 5, 2 better, 2 worse, 1 neutral.
A full-corpus bound is cheap -- `_pierce_seams` fires without rendering.

**`35480-bore-reads-flat` is waiting on Mike and nobody else.** Looking down a
bore, `max(0.0, n . L)` in `shade._axis_binned_stops` floors every bin past the
terminator and a quarter of the visible tube pins to one tone. Fixing it is a
lighting-model change that moves every render in the corpus.

**`tests/goldens/defects.toml` carries four rows written this session and is
unstaged by design.** It is Mike's file. If it is ever reverted, those rows go.


## Baton, 2026-09-07 evening: occt drops naive's decal unwrap, and the audit that follows

**Do this first: go through the naive engine's tricks and check each has an
analog in occt.** Mike's ask, and the one below is the first row of that table
-- found by reading the two call sites side by side, so the rest of the audit
is the same exercise over `hlr.py` against `occt.py`.

**`occt` hands `unwrap_decoration` an empty carrier list and throws away the
recovered ellipses; naive passes both.**

    hlr.py:523   shade.unwrap_decoration(tri_faces, analytic, proj,
                                         ellipses_out=decal_ells)
    occt.py:1621 shade.unwrap_decoration(faces + deco, [], proj)

`unwrap.py` already IS the "scrape the decal off and draw it back as one
piece" machinery Mike asked for -- it maps a decal into its carrier's
parameter space, unions it there at full precision, and re-projects onto the
exact surface, dissolving the author's faceting on the way (its own docstring:
3941p01's 36-quad panel becomes one rounded rectangle in (theta, h)). It
covers planar, cylinder and cone. On occt the analytic carriers never reach
it, so a decal can only bind to a plane OCCT happens to have built, and
`ellipses_out` -- the planar arc recovery for printed shapes -- is collected
nowhere.

**Two parts to work against, both from tonight's sheets.** `004490h`
("WANTED DEAD OR ALIVE"): the bottom line of small text draws as dashes and
dots where LDView draws letters, and the rule under it is dotted. Setting
`shade.RESIDUE_CRUMB` to 0 recovers some glyph pieces and NOT the start of the
line, so the crumb cull is a contributor and something upstream fragments it
too -- do not stop at the cull. `003428d` is Mike's named case for planar arc
recovery: an oval printed plate whose decal circles should come back as arcs.

**Tonight's landed work is `73af254`, pushed.** occt_faces built no face for
any non-round disc or ring; 2,619 of 24,591 parts carry one. All 576 parts
with a stored `silhouette-occt` render were re-rendered (`ellip-restage`, plus
a 10-part retry at MEM_GB=12 for the ones the 4GB cap killed). 523 of 576
moved: 135 changed the silhouette, which is this fix; the other 388 only
repainted inside an unchanged silhouette, which is the coplanar paint-order
fix landing, not this one.

**`out/ellip-before/` is the only copy of the pre-restage SVGs and is
untracked.** The originals were overwritten. Without it the before/after
sheets in `out/restage/ellip-sheets/` cannot be rebuilt.

Still returning `[]` from `occt_faces`, each its own problem: an elliptical
`con` (four of them are `71689`'s residual 233,860 missing px) and a skew
axis (`4609`'s 149,786).


## Baton, 2026-09-07 afternoon: what is running and what to do first

On `main`, in the shared checkout. `git log --oneline @{u}..HEAD` for anything
unpushed; nothing of mine is uncommitted.

**Do this first: measure how many stickers the coplanar paint-order fix
actually changes.** `a38e5a8`, gated to same-color pairs by `83ba303`. The
whole `4263304` family reads as fixed at HEAD and broken in the stored
`silhouette-occt` renders -- `4263304a` stored says `SF` and draws `BNSF` at
HEAD, `c` says `56` and draws `2256`, `d`'s cross is gray and draws yellow, `f`
draws one lozenge of three, `g` draws fragments of two vent panels, and
`ec01`'s far half is blank. The question is the size of that class over the
4,513 sticker parts. **Do not measure it with a census** -- paint order changes
which color wins INSIDE the silhouette and `compare-silhouette-truth` scores
`alpha > 128`. `scripts/render-hash.py` hashes the rasterized RGB under the
alpha mask and is the tool; `scripts/hlr-shell-affected.py` is the model for a
cheap in-process A/B that toggles the fix's own constant. **`brick-icons-00` is gone**, so nobody
can be asked about its A/B; its `ab-control` output is on disk at
`out/abhash/ctl-printed/` -- 2,812 parts, 2,794 ok, and 2,808 of them stickers,
which makes it the control half of this exact class. It was taken by checking
out `coplanar-control`, not by an in-process toggle, so it carries the
editable-install question: a cross-check, not an input. The branch must not be
deleted.

`4263304ec01` is the one still wrong at HEAD: the formed sticker's near flap
reads flatter than LDView's and the arrow loses part of its fill. Its own row
if anyone wants it chased.

**Two jobs were running when this was written** -- `onto jobs` for the truth.
`hlr-restage-list` (orochi, 6 shards) writes `restage/hlr-loose-faces.txt`,
the re-render list for `b350c40`; when it finishes, re-run
`scripts/hlr-shell-affected.py` over `out/restage/occt-parts.txt` with
`--log` pointed at the merged shard logs and `--out restage/hlr-loose-faces.txt`
and the resume path does the merge for you. `ldview-bake` re-bakes the LDView
thumbnails; it skips anything unchanged.

**Three other sessions share this exact working directory** and one more is in
the `defect-sweep` worktree. Stage explicit paths, never `git add -A`, and
confirm the branch before assuming it. `tests/goldens/defects.toml` is Mike's
and is permanently dirty; `lab/src/corpus/badges.ts` is `brick-icons-de`'s
badge work in flight.

## The slots lost `census-`, and the LDView gap is stickers nobody rendered

`5df13cb`. Every slot came out of a census run, so the prefix said nothing:

    census-occt        -> silhouette-occt   (strokeless; fills carry the outline)
    census-naive       -> silhouette-naive
    census-white-occt  -> white-occt        (opaque white fills, strokes drawn)
    census-white-naive -> white-naive

`occt` and `naive` keep meaning flat3 with 2px strokes -- Mike's call, against
handing those names to a different config. Both are still empty.

**A census TREE is a directory and a slot is a slot, and they used to share a
name.** The directories are all still `census-something`; `db.census_source`
now reads the facet out of the directory name and `index-census-renders.py`
keeps `TREE` and `SOURCE` apart. `renders` and `measurements` rows are
migrated and `out/thumbs/<slot>` is renamed, so nothing re-renders or
re-bakes. Anything holding a slot name -- a script, a saved URL, a lab
bookmark -- needs the new one.

**The uncommitted `labelX` change in `lab/src/corpus/badges.ts` is
`brick-icons-de`'s** -- it was launched to take over the lab's badge rendering,
which its own process argv says. Leave it alone. Two sessions guessed at the
owner before anyone read that: `ps -eo pid,command | grep '[c]laude'` prints
every session's launch prompt and settles it in one command.

**The LDView slot is complete: all 24,591 parts.** The 2,794 that were
missing -- 2,701 of them stickers -- were coverage the slot never got, not
anything refusing to draw: they render at 0.2-0.6s each, in color, artwork
intact. Filled on studio as task `ldview-fill` (112 batches of 25, 5 workers,
about four minutes), fetched, indexed, and the thumbnails re-baked. Four parts
(`11055df1`, `11244p05`, `11408p03`, `11477d0u`) had a database row pointing
at a file that was gone, so they were not in the missing list either; drawn by
hand and now present.

**`census-ingest.sh` rebuilds `corpus.db` every 900s and it is the authority.**
It rebuilt three minutes after the hand ingest and replaced it, keeping the
24,002 files that were on disk when its scan started and dropping the 589 that
the final fetch delivered mid-rebuild. Nothing was lost -- the files are the
truth and its next pass indexes them -- but a hand ingest races it, so either
index into it or wait a pass and check, rather than trusting a count taken a
minute after a swap.

## Defect sweep, 2026-09-07 midday: the borehole class closed, and where the rest stand

`b350c40` closes "something occluded is drawn anyway" on occt. **HLR reads a
face's orientation once the faces are connected in a shell and lets a
back-facing one occlude nothing** -- and `build_shape`'s sewing leaves an LDraw
part inward, so its own front faces stop hiding anything. 79306-f1 drew 3 LDU
of its bore's limb straight across the end annulus that hides it; ray-traced,
every point of that run is occluded, and the run stops exactly where the outer
wall takes over. `hlr_edges` now hands HLR `_loose_faces(shape)`, the same
faces in a compound. **Reversing the shell fixes 79306-f1 too, and so does an
oriented solid; neither generalizes** -- both need a closed volume, which a
cracked part is not.

Closes `79306-f1-far-end-should-be-hidden`, `4913-hole-in-base-shows-through`
and `14653-f1-left-hole-should-be-invisible`; takes the two arcs that cut
across 96904's recess floor, one stray arc off 53119's base ring, the
scallops off 3062b's stud collar and the crescent sliver out of every one of
3894's Technic holes. Outline and shaded alike, each read against LDView.

**A differing SVG is not a moved drawing here** -- this change reorders
elements, so 11090 and 59443 differ byte for byte and rasterize identically.
Rasterize and diff before crediting it with anything.

**Bounded on 137 sampled library parts: 44 differ in bytes, 29 move a pixel,
and not one moves for the worse.** 15 of the 44 rasterize identically. Of the
29, 26 lose strokes; the 2 that gain one -- 44302a and 5091 -- gain it where
new occlusion splits a run in two. All 29 were rendered and looked at: the
crescent inside a bore, the scallop over a stud collar, one big phantom
ellipse inside 77813's ring. No errors, and no measured cost in time on either
side. Job `01a6b72d`, task `hlr-shell-ab`, still grinding on 71986 (an 11L
ribbed hose, slow on both sides) when this was written; the remaining 22 parts
add nothing the first 137 have not said.

`59443-a-strip-along-the-bottom` reorders its SVG under the fix and is pixel
for pixel identical, so that row is untouched.

**4070 is byte-identical under it and its verbal description is wrong.**
LDView's "hexagonal recess" is `-AllowPrimitiveSubstitution` drawing the r=4
`4-4cyli` at low curve quality; the innermost ring is a real circle, the
`stud2a` collar's inner rim. What ours actually misses is the recess behind
it -- nothing at all is drawn inside the collar bore where LDView shows wall.

### The re-render list, and how to get one for the next engine change

`scripts/hlr-shell-affected.py` names the parts `b350c40` moves without
rendering any of them: HLR twice a part, shell against loose faces, visible
edge sequences compared, 0.3s against up to 40s for two renders. Against a
full render A/B of 160 parts it caught all 49 whose SVG changed and named 13
more that did not -- a superset by design, because a wasted re-render costs
seconds and a missed one leaves a stale drawing on the wall. Its output is
`restage/hlr-loose-faces.txt`, and it feeds

    .venv/bin/python scripts/build-render-store.py \
        --list restage/hlr-loose-faces.txt --sources occt --force

**Compare the SEQUENCE, not a sorted set.** Sorting first looked like the
honest comparison and missed 9 of 33 parts whose pixels move: the stages under
HLR read ops in order, so the same edges in a different order still trace
differently. That is the same trap as reading a byte diff as a moved drawing,
from the other side.

### 2310 and 39789 are confirmed and neither is a hidden-line miss

Both were ray-tested against the shape occt itself builds, with
`IntCurvesFace_ShapeIntersector` and the projector's own view direction --
**HLR's answer is right for that shape in both.** So the disagreement with
LDView sits upstream, in which surfaces reach HLR at all, and no visibility
rule will move it.

- `2310` -- naive draws it stroke for stroke the same, so it is not an occt
  fault at all. `compare-silhouette-truth` gives 0px missing against the
  part's own triangles, so our outline is exactly our geometry. What LDView
  shows is a flat wall where both engines draw a half cylinder: the r=6
  circle at (0,12,0), which is outside the material in every direction tested
  (every ray count even). Its filed engine list should say `naive` too.
- `39789` -- occt alone draws four ~85-degree arcs of the r=8 recess rim at
  each of the three axle holes, curving across the stud in front. naive draws
  none of them and LDView shows none. Ray-tested, 34 of 36 samples of what
  occt draws are genuinely clear to the camera in occt's shape, and the 2 that
  are not sit at exact tangency. The lead is the occluder set: compare what
  `occt.build_shape` holds against `primitives`' occluders for this part.

### The constant stroke width is the biggest remaining cause, and it is already filed

Rendered at `--line-width 1 --silhouette-width 1` against the 2 the config
ships, all shaded, all read against LDView:

**`38317-left-stud-shading-is-very` is that and nothing else.** At 2 its two
studs are solid black lozenges -- four `#000000` pockets out of seven fills in
the SVG, the junction-lens inking filling what the strokes leave -- and the
right one carries black bars across its wall. At 1 both are clean rings. It
is not a shading fault; re-file it under `3832-doubled-stud-ellipses` /
`65068-studs-drowned`, on occt.

`96904`'s fat slot and `96910`'s heavy insets lighten at 1 and still sit
wider than LDView's hairline, so they are that class plus something else.
`39789`'s bracket arcs are unchanged at 1, which is the other half of the
ray-test finding above: they are real geometry, not ink.

**The class reaches both engines and every part small in its own frame**, and
the filed measurement (3832) is naive-only and from before the switch. Fixing
it means scaling the stroke to the drawing rather than pinning it at 2 output
px -- which moves every render in the corpus, so it is Mike's call, not a
session's.

### Every occt row, rendered at iso and read against LDView

Confirmed, still open, worst first:

- `49492-occt-deletes-several-extruded-segments` -- **the crook is barely
  drawn**: a thin malformed loop where LDView has a fat smooth hook. The part
  is `t16o`/`t16i`/`t04o`/`t04i`/`t16q` and nothing else round;
  `occt_faces` handles `edge`/`cyli`/`con`/`disc`/`ring` and no torus, so all
  of it falls to tessellation. Same for `3484-occt-handle-missing-arcs-extra`
  (its fork is drawn straight-sided, cavity gone) and
  `35485-ring-is-broken`, both of which are `s\*s01` subfiles plus a `cyli`.
  Analytic torus is the shared answer and it is a feature, not a fix.
- `2310-crap-on-darkest-face-and` and `39789-occt-has-issues-with-top` --
  both confirmed, both diagnosed above; neither is a visibility fault.
- `92692-joint-where-front-tube-meets` -- the tube/ring joints read as
  separate capped cylinders.
- `96904` keeps its slot drawn far fatter than LDView's hairline; the annulus
  itself is present and always was.

Shaded-only, so `--shade-style flat3` is needed to judge them and an outline
render says nothing. All three now rendered that way. `38317` and
`96910` are the stroke-width class above. **`35480` is FIXED by `f832da6`,
and the earlier reading of it here was wrong** -- absorb never ran on the
part. Its two fangs were a bore drawn where it is buried inside the plate:
UnifySameDomain merged the stud's `stud2a` with the `4-4cyli` continuing below
the plate top into one face straddling that plane, and `order_faces` gives a
pair one bit. `_pierce_seams` keeps the seam. Buried-bore ink on the plate top
is 0.00 px^2, against 605.17 for the lobe and ~42 for the limb fangs;
`debug/35480-pierce-seam/verify.py` reprints those against the tree as it
stands. Diagnosed independently by two sessions.

**What it does NOT close: `_refine_order_clips` is one-directional.** It hands
back area a face wrongly lost and there is no pass that takes away area a face
wrongly kept, so any other cycle break that drops a constraint still leaves
ink with nothing downstream to remove it. No part shows it right now, so it is
here rather than in `defects.toml`.

**Two rows filed off the back of it, both `35480`, both open.**
`35480-bore-reads-flat` is the one that needs Mike: looking down a stud the
tube has no depth because `max(0.0, n . L)` in `shade._axis_binned_stops`
floors every bin past the terminator, and looking down a bore puts the
terminator mid-span. Fixing it is a lighting-model change and moves every
render in the corpus, so it is his call, like the constant stroke width --
check a Technic pin hole first to scope it. `35480-wall-fill-hairline` is the
visible fill-fragment seam on the plate's outer wall; `f832da6` moved it one
pixel without touching it, which is what makes it worth a row.

`11090-curved-lower-face-in-occt` and `11090-hand-at-top-is-missing` are
`9fdfb72`'s alone (the sheared cross-section), pixel-identical under this fix
by both sessions' measurement, and belong to whoever filed that commit.

`53119`'s two ticks on the dome survive. Its banding half closed overnight.

## The badges: 1 and 2 are landed, the wall is still a hand-written paint loop

`f721151`. The three defects Mike reported had one cause and two of them are
gone.

**The marks are path data now.** All twelve live in `lab/src/corpus/markShapes.ts`
as SVG path strings with a fill/stroke/alpha spec; `badges.ts` fills them into
a canvas and `BadgeSwatch.tsx` emits them as `<path>`. **Nothing in the set is
allowed to be a draw call again** -- that is what put a rasterizer behind the
legend. Two escapes are declared rather than baked, and both are load-bearing:
technic keeps a `transform` because a shear thickens a stroke's pen and baking
the shear into the endpoints would not, and the sticker's peel keeps `punch`,
which is `destination-out` on the canvas and a mask in the DOM.

**The Legend, `tags.tsx` and the Lightbox status are HTML.** `BadgeSwatch`
renders a CSS stadium with the mark as inline SVG; `labelX` is gone from that
path entirely. The peel's hole is a CSS `mask-image` with two layers and
`mask-composite: exclude`, because what it cuts is the field, which the disc's
`<svg>` does not paint.

**The misaligned text was `measureText`, and it is fixed on the canvas too.**
`actualBoundingBoxAscent` is reported FROM the current baseline, and
`drawBadgeDirect` measured the label under `middle` and painted it under
`alphabetic`. Measured on the render, not on the formula: the word sat 7.0
device px high on a 17px badge and 18.0 on a 44px one -- a constant fifth of
the badge, which is why it looked like a fixed offset at one size. Measuring
under the baseline it paints on brings the canvas to within 1 device px of the
HTML. **The earlier note that the arithmetic was provably exact was measured
with the default baseline in force, not the one the code sets.**

**A/B, in process, both paths from one set of badge records:** nine of twelve
marks are byte-identical on the canvas; the other three (archive, minifig's
eyes, the sticker's cap) differ only in antialias coverage where a rect or an
arc now rasterizes as a path -- 185 px of 756,000, worst channel delta 47.
A moved shape would read 255 where white ink meets a gray field.

Also landed: the scratch canvas is allocated at dpr, which is what made the
sticker badge alone render soft; `Path2D` objects are kept per path string
rather than reparsed for every badge on a wall paint.

### Next: the wall's paint loop becomes weasel's scene, on `wall-scene`

**Branch `wall-scene`, worktree `.claude/worktrees/wall-scene`.** Both exist.
Mike asked for this one off the shared tree because four other sessions are in
`/Users/mike/src/brick-icons` and the wall is the file they are most likely to
touch. Run `npm install` in the worktree's `lab/` before trusting a test run --
a symlinked `node_modules` shares `node_modules/.vite`, and a stale cache there
serves modules from the wrong tree with no error.

`Wall.tsx:594` is a bare `<canvas>` with a hand-written renderer; the lab
imports weasel only for viewport math (`worldToScreen`, `zoomAt`, the drag and
pinch actions). `@weasel-js/core` exports `createNode`, `ContainerNode`,
`ImageNode`, `LeafNode`, `drawText`, `renderSceneToCanvas`, `registerCanvas`
-- **`grep -rn "renderSceneToCanvas\|SceneNode\|createNode" lab/src` still
returns nothing.**

**Mike wants old against new benchmarked, and that decides the shape of the
work: the hand-written loop stays, behind a flag, until the numbers are read.**
A sequential A/B measures the box and not the change -- that is already filed
twice in this repo, once at 36x against 18x for the same commit and once at
0.90x on a peer's machine. So the two renderers have to be alive in one process
and interleaved, alternating paints rather than running one suite then the
other. Deleting the old loop first makes the measurement impossible to take.

What to measure is a full wall paint in ms, at a fixed corpus, cell size and
camera, across the zoom levels that change what gets drawn (thumbnails, then
badges and captions, then vector). Report one line per paint as it runs; a
silent harness is indistinguishable from a hung one.

**One thing the new renderer must not give back:** badge marks are path data
now, and `badges.ts` keeps one `Path2D` per path string rather than reparsing
about thirty of them for every badge on every paint. `drawText` is the reason
to do this at all -- it is where the baseline arithmetic belongs -- but a scene
node allocated per cell per frame would cost more than the loop it replaces.

**Look at the badges at `/badges.html`, not at a description of them.** It
draws every badge as HTML at four sizes on a light ground and a dark one, the
real `<Tags>` row, the status pills, and the canvas sheet underneath. The
sticker's peel is a hole, so it is invisible against a ground its own color --
that is what the two grounds are for.

## 2026-09-07 late morning: coplanar paint order, and an A/B the census cannot run

Merged to `main` (see `git log --oneline --first-parent -8`): the coplanar
paint-order fix, an RGB render-hash sweep, an orthographic reference renderer,
cmd-0, and `DEVELOPING.md`. Branches `coplanar-order` and `ortho-reference` are
merged and disposable. **`coplanar-control` is not** — see below.

**Stickers lost half their artwork to the paint sort.** `shade.order_faces`
skipped every coplanar pair with `continue`, adding no ordering edge, so the
ready-heap's mean-depth tiebreak decided. A decoration blob on a tilted face has
a mean depth that lands either side of its background's, so artwork in the far
half sorted behind its own background and vanished — Mike's "it works on exactly
half". Measured, mean depth contradicts file order in 7 of 12, 5 of 7 and 1137
of 2195 coplanar pairs on 6155286u, 6148328ak and 6177969acc01. The fix orders
coplanar pairs by list index, which is file order because `_with_decoration`
appends decoration last, and LDraw draws decoration after the surface it sits
on. 6148328ak gets its red border back; 6177969acc01's checkerboard resolves.

**The census cannot see a change like this, and this is the load-bearing
decision of the session.** `compare-silhouette-truth` builds `ours` as
`alpha > 128`. Paint order changes which color wins *inside* the silhouette,
never whether a pixel is opaque, so a full census would have returned
near-identical numbers whether the fix was right or catastrophic. Mike asked for
a census pass; what is running instead is `scripts/render-hash.py`, which hashes
the rasterized RGB under the alpha mask. Do not "correct" this back to a census.

**The A/B is half done.** `ab-control` (job `edbad6eb`, studio, deadline 7:06PM)
sweeps all 8235 parts at the pre-fix revision, into `out/abhash/control`, with a
fetch stream running. Still owed: sync the fix revision and run the same sweep
as `ab-fix` into its own directory, then diff the shas — the parts that differ
are exactly the parts whose drawing moved.

The two revisions must differ **only** by the fix. `coplanar-control` is
`f41a962` plus the sweep script and nothing else; the fix side is `f41a962` plus
those plus the one `shade.py` hunk. Do not sync `main` for the fix run — `main`
carries 23 other commits since `f41a962`, several of them engine changes, and
using it conflates them into the diff. Keep `coplanar-control` until the A/B is
read.

**The goldens are green, and the earlier red was mine.** The first version of
the coplanar rule applied the index tiebreak to *every* coplanar pair, which
also reordered two faces of the same body — `3005`'s stud wall and the top face
it stands on are coplanar where they meet, and index order painted the stud
under the brick. That broke
`tests/test_occt.py::test_the_stud_paints_over_the_top_face_it_sits_on` and
drifted `outline-flat3__3005`; `brick-icons-c6` caught the unit test. The rule
now fires only when the two faces carry different colors, which is what makes
one decoration on the other and the only case where LDraw's emission order is
an instruction about paint order. Sticker renders are unchanged from the broad
rule; goldens need no re-freeze.

**LDView stays.** Mike said "we're ripping out ldview" and then reversed it an
hour later: leave it in so the new orthographic renderer can be compared against
it. The new one (`lab/shot.html`, `lab/src/shot/shot.ts`,
`scripts/shot-sink.py`) is merged but unfinished — the key light is a guess at
LDView's `-LightVector` rather than the ortho path's own `--light` convention,
there is no part-color override, and it has no `db.SOURCES` slot, so it is not
a wall column yet. It works: one browser draws a list in one WebGL context.

**Mike named a fourth case of "occluded thing drawn anyway", verbally, so it is
in no defect row: 4070.** Its icon draws three concentric circles at the bore —
collar outer edge, bore mouth, and an innermost ring that should not be a circle
at all, because the bore interior is the hexagonal LDraw recess and its far
geometry sits behind the near wall. He said it generalizes: "there are lots of
cases where there's a borehole somewhere that we're not properly occluding".
Worth testing against `79306-f1`, `4913`, `14653-f1` and `59443` as one fault
rather than four. Note the older finding that 4070's *dropped ledge edge* is an
HLR visibility misjudgement with 0 ABSENT edges — that is the same stage failing
in the other direction, culling what it should draw.

**Queued and unstarted:** Mike reports the translucent renders are "too fancy
and are culling surfaces that need to be rendered now because everything needs
to be rendered in this mode". Nothing has been looked at.

**cmd-0 is unverified by test.** It now clears `camInitialized` so the zoom
level resets and not just the camera. jsdom does no layout, so the refit yields
an identical camera object, neither branch of the level effect runs, and a test
written against `pickLevel` or `levelFor` passes with the fix reverted. It needs
a real browser or nothing.

## 2026-09-07 midday: a sheared cross-section is an ellipse, not a reject

`9fdfb72`, on occt. `frame()` lumped two unrelated defects together and
dropped both. They separate cleanly:

- **A skew axis** — the axis column leaves the cross-section plane — really is
  unrepresentable, because there the axis is the extrusion direction. Still
  rejected. 18% of parts carry one; 10126's oblique cylinders are the open
  question, unchanged.
- **A sheared cross-section** — `u` and `v` not square to each other, axis
  fine — is an exact ellipse, because a linear map sends a circle to one. It
  is now diagonalized: the singular values of `[u v]` are the semi-axes,
  and `frame()` returns a ninth element, the phase that keeps the sector where
  the part put it. Drop the phase and 11090's quarter swings 135 degrees.

11090 is the part that showed it: its tube wall is two `1-4cylo` at 89.2
degrees. Rejected, the wall reached the kernel as **neither a face nor
triangles** — `hlr.flatten` recurses into a subfile only when
`primitives.from_ref` does *not* recognize it, so a substituted primitive that
then builds no face leaves nothing at all. The base drew as a hole with the
bore floating inside it. 51482 also loses a hidden edge that was leaking
across its knurled boss.

538 primitives across 52 of 800 sampled parts were rejected for shear alone,
so this reaches roughly 1,600 parts. No specimen carries one, which is why the
corpus never saw it — and also why the corpus cannot guard it. **11090 is
worth adding to `specimens.txt`**; nobody has, because freezing while the gate
is red would tangle it with whatever is red.

**The `=full` gate is red on 31 rows, not one.** Every one is a naive-engine
row (no golden combo passes `--engine`), so occt work cannot move them and
this is drift from naive-side changes that landed without a re-freeze. The
list: `outline-flat3__` 3001, 3005, 3020, 3024, 3040b, 3040bp08, 3068bp00,
32062, 3649, 3673, 3941, 3941p01, 3942bp01, 3960, 4019, 4070, 4589, 4740p03,
50950, 6143, 6589, 87087, 99781; `outline__` 3001, 3941, 3942c, 4589, 6143;
`wireframe__` 3001, 3941, 4589. Whoever re-freezes owns deciding whether each
is an improvement.

**11090's second defect is real and untouched by this.**
`11090-curved-lower-face-in-occt` is the base, closed. `11090-hand-at-top-is-
missing-a-curve-too` is the clip, and it is a different fault: **in the clip
region occt draws 3 arcs against naive's 7**, unchanged by the fix above (3
either way, 8 pixels of antialias). The one to look at runs the length of the
clip's right lobe — the limb where its 225-degree cylinder turns away.

Count arcs by region on this part, never over the whole drawing. Whole-part it
reads 3 against naive's 8, which looks like the clip gap and is not: the fix
above takes occt's base arcs from 5 to 0, and those 5 were bore limbs only
visible through the hole in the wall. Naive draws 1 base arc there, so the
base is a separate 1-arc gap, the short curve at the collar.

`tests/test_occt.py::test_the_stud_paints_over_the_top_face_it_sits_on` fails
at HEAD with nothing applied (`assert 12 > 13`) — it belongs to the coplanar
paint-order thread above, not to this.

**Diff renders composited onto white.** A `--shade-style none` SVG has a
transparent ground, and resvg leaves the RGB under it at zero, so
`Image.convert("L")` reads the whole frame as black and every diff comes back
0 changed pixels. Two comparisons here read as perfect agreement that way and
were 1040 and 2598 pixels once composited.

## Overnight defect sweep, 2026-09-07: what is fixed and what the rows are lying about

Mike asked for a night on `tests/goldens/defects.toml` and the census's failed
parts. Branch `defect-sweep` (pushed, `origin/defect-sweep`) holds two commits
off `84b1706`, both a clean fast-forward onto `main`; `brick-icons-11` was asked
to merge them, because `main` is checked out in the shared tree and a worktree
session cannot move it.

- `d8181bf` **GEOSException is fixed.** `shapely.clip_by_rect` is GEOS's fast
  rectangle clipper and does not check its input: handed a polygon carrying a
  zero-area interior ring it builds a 3-point LinearRing out of that hole and
  throws, on input GEOS itself calls valid. 813c03-f2's fill carries a
  three-point hole of area 4e-13. `geom2d.window()` falls back to intersecting
  with the box, and shade's four `clip_by_rect` sites go through it. It is
  deliberately NOT the module's `_only_area` intersection — one caller windows a
  MultiLineString, and stripping that to empty is a wrong answer, not a safe
  one. Reachable only where the old code raised. 813c03-f2 draws its rails,
  sleepers and uprights correctly now.

- `0a39ae8` **Gradient banding is fixed, and the filed cause was wrong.** The
  linear path emitted a stop per facet through `style.ramp(nv)`, so two facets
  at nearly the same offset and opposite azimuth wrote two tones and the run
  ALTERNATED between them. 44300's chamfer band: 67 stops, two colors, hairline
  stripes across the fillet. `curved-surface-gradient-banding` proposed "merging
  equal-color runs"; that would not have touched it, because the tones alternate
  rather than repeat. `_axis_binned_stops` bins by offset, averages BRIGHTNESS
  in the bin and ramps once — exactly what the radial path already did. 44300 is
  now 10 stops over 4 tones and one flat surface; 7037's rounded face loses its
  striping. Cylinder-wall ramps are unchanged to the eye at 6x (3062b, 3005),
  and a unit test pins a monotone sweep against being flattened.

  Closes `7037-gradient-banding` and `curved-surface-gradient-banding`, and the
  shaded half of `53119-occt-has-a-bunch-of`. Its stray lines are untouched.

### `outline__3673` was stale, not broken — and the gate is why nobody knew

Resolved and re-frozen in `145c345`. It read as a naive regression: an arc and a
subpath gone from the strokes-only combo, which is the one that exists to catch
that. Bisected over 323 revisions, eight steps, with the freeze of that single
case as the test — first bad commit `1d0450b`, "run the orphan cull on the occt
path, and drop floating islands". Rendered either side, the dropped run is one
2-output-px dot on the pin's barrel: the rule working, on exactly the case it
names. The drawing is better without it.

**The bookkeeping is the finding.** `BRICK_GOLDENS=1` freezes 3005 alone, so
every other row in `hashes.txt` is decorative until someone runs `=full`. For
three days nobody did, and the corpus described a pre-`1d0450b` engine.
**`=full` is the only run that bounds a `shade.py` or `hlr.py` change**; a green
`=1` does not, and should not be cited as if it did.

**The island threshold has room on both sides.** It is relative — a run under
1.2% of drawn extent goes whatever its kind — so the parts it can reach are
those whose real features are small against their overall size, and a pin is the
worst case. Instrumented and swept over all 22 specimens on both engines, 133
candidate islands: the three dropped are 1.077% (3673 naive), 0.902% (3941p01
occt) and 0.585% (6589 naive); the smallest one KEPT is 6.988% (99781 occt).
The threshold could sit anywhere between 1.1% and 7% and change no decision on
this corpus. That bounds the specimens, not the library — a census-scale answer
needs the same counter and a fleet run.

`tests/goldens/defects.toml`'s uncommitted block is **Mike's**, not any
session's: `brick_icons/lab/defects.py` rewrites the whole file on every filing
from the lab UI. Do not commit it.

### The split-arc class is a naive-only defect, and occt already draws it right

Started, not finished. `4524-ring-whole-circle` / `27448` / `30152a` are filed
`engines = ["naive"]`, and an LDView A/B at iso says that is the whole story:
naive draws 4524 as a phantom raised collar — four concentric ellipses, the
bore's bottom rim nearly whole and offset well below the top rim — where LDView
has a flat plate whose hole shows one thin crescent of far inner wall. occt
draws it essentially as LDView does. Since occt is the engine of record, this
class is worth much less than three filed entries suggest; the entries predate
the occt switch. Picture is on the slopboard, `brick-icons` zone.

Naive's arc ops for 4524: two full ellipses at cy 414 (the top face's bore rim
and outer rim — correct, that face is wholly visible) and partials at cy 500
(146 deg) and cy 580 (261 deg). So `dedupe_segments` is not unioning spans into
a whole circle; the underside rims survive occlusion they should not, and the
"whole circle" reading in the entry is a symptom rather than the rule. Anyone
picking this up should re-file it against what the A/B shows, or close it as
naive-only.

**The one thing both engines get wrong is a stray tick inside the bore** — a
short mark across the hole on 4524, on naive and occt alike. That is the same
shape as `30152a-annulus-dots`, which was deliberately filed apart from the
split-arc entry on the same part. That separation looks right, and the tick is
the part of the class that survives the engine switch. It is the piece worth
taking.

### The census's failure rows are stale, and "stale" is not "fine"

Latest run per part, on occt: TimeoutError 413, ProcessDied 243, TypeError 29,
LinAlgError 4, ValueError 3, RuntimeError 2, GEOSException 2.

All 29 `TypeError: coordinate list must contain at least 2 coordinates` rows are
build `830.557ae4d` and the crash is gone. **Do not read them as clean.**
Re-running them at HEAD under a 120s cap: 2393, 4273a, 32208 and 15092 draw,
while 15461, 18942, 19086, 19159 and 28578 now hit the TIMEOUT instead. The
crash became slowness on at least five. Same shape as `6177970ec01`'s
ProcessDied: re-derive a failure row before quoting it.

Also verified healed at HEAD: the three `ValueError` stickers (4221407f,
4510086c, 6015425b) by `c673dd3`, 6342851a by `b5b2694`, 5241, 2976c01 and
72632. Still failing: 41896c01 and 72632c01/c02 on time, not on a crash.

## Read first, 2026-09-07 early: occt only, and where the wall stands

**occt is the engine from now on**, until Mike says otherwise. Say "on occt" in
any report so a naive number is never mistaken for the current one.

**Several sessions share this exact working directory** -- `ListAgents`, or
`node ~/.claude-msb/skills/pass-the-baton/baton.mjs successor --since 0`, for
who is here right now; the roster turns over hourly, so do not trust a list
written down. Same tree: their uncommitted edits appear in yours and
`git switch` moves the branch under all of them. **Stage explicit paths; never
`git add -A` or `git commit -a`.** Confirm the branch before assuming it.
`git log --oneline @{u}..HEAD` for what is unpushed; `git status --porcelain`
for whose work is in flight.

**Vitest does not typecheck, so a green suite is half an answer.** Run
`npx tsc -b --noEmit` in `lab/` as well. `main` was red on
`lab/src/corpus/Lightbox.tsx` for a while tonight and is clean again as of
`931b342` -- the point is the habit, not that one break.

**Nothing of mine is in flight.** Every change described below is committed
and pushed.

**`tests/goldens/defects.toml` is dirty because the lab writes it, and it is
Mike's file, not a session's.** `brick_icons/lab/defects.py` holds
`DEFAULT_PATH = tests/goldens/defects.toml`, and the `add`/`update` routes
write the whole file straight back to disk -- so every defect filed through the
lab UI lands there uncommitted. Three sessions in one night each read those
lines as a peer's work in progress and stepped around them. Nobody should
commit that file but Mike. If you have a correction to an entry, make it in the
tree and say so; do not stage the file to carry it.

**`corpus.db` and `out/thumbs` are rebuilt and current, and neither is in
git.** They already hold the sticker renders and the ldview slot, so a fresh
ingest buys nothing -- and `scripts/census-ingest.sh 900` may be looping in
another session, which is the one thing not to race. Check `pgrep -fl
census-ingest` before starting one.

**The `naive` render store is gone on purpose** (`6078305`), at Mike's ask. All
49 of its parts are drawn by census slots too, so it covered nothing on its
own. It stays in `SOURCES` and `_CANONICAL`, so with no rows it just stops
being listed. It is a committed deletion, not lost files:
`git checkout 6078305^ -- renders/naive` restores all 49. A `git ls-tree HEAD`
coming back empty is what a committed deletion looks like, not proof the files
were never tracked -- that reading cost a peer a false alarm.

**Every sticker draws now, and the last five were three separate faults.**
`43e09bd` and `cdb54ee` built the undeclared-edge fallback and took the
2,701-part bucket to 2,695. `c673dd3` and `b5b2694` finish it. All five were
rendered and looked at: each draws its plate outline, no facet cloud.

- `4221407f`, `4510086c`, `6015425b` -- `ValueError: need at least one array
  to concatenate` out of `cull_orphan_runs`. OCCT's entire visible edge set
  for each is two 0.22 LDU stubs, the plate thickness seen edge-on at the far
  left and far right. They sit at opposite ends of a 276-314 LDU bbox, so the
  ghost length lands at 0.55-0.63 and no op clears it; `real` came out empty
  and `np.vstack` had nothing to stack. The cull only ever removes, so with no
  stroke graph it now returns the segments untouched.
- `6342851a` -- "produced no edges". A `box5-12` plate with 8,888 artwork
  triangles coplanar on its top face and two type-2 lines drawn along the
  print. UnifySameDomain merges all of it into 6 faces, so both lines land in
  the INTERIOR of one and match none of HLR's 9 visible edges. **A declaration
  only counts where OCCT has an edge to hang it on**, so the fallback's guard
  is now that nothing was drawn, not that nothing was declared. This
  deliberately reverses `cdb54ee`'s "a real type-2 and still nothing is a
  different fault and still raises" -- 6342851a was the only part in the
  census on that row (5241, the other, has drawn since `43e09bd`) and it is
  not a fault. Restore the guard by putting `and not out.get("2")` back on
  `occt.visible_segments`'s fallback line.
- `6177970ec01` -- nothing wrong with it. Renders in 90 s at 823 MB peak. Its
  `ProcessDied` row is exactly the stale-row trap below: collateral from a
  pre-`18310b7` runaway that named whichever part held `.inflight`.

Both fixes are byte-safe by control flow, not by sampling: each branch is
entered only where the old code raised. (`43e09bd`/`cdb54ee` were measured by
instrumenting `occt._undeclared_ops` -- a byte-diff against a worktree does
not work here, because the editable install beats `PYTHONPATH` and both sides
run HEAD.)

## The dashboard now says where the time goes and what it costs on disk

Two things Mike asked for tonight, both landed and pushed. `git log --oneline
@{u}..HEAD` for what is unpushed; the commits are `a11741a` (phases),
`9f9282b` (footprint) and `2d25603`.

**A phase records under the path of the phases open around it**, and a
parent's time now INCLUDES its children -- `render/geometry/engine/hlr`. The
nested-subtraction the old accumulator did is gone with it: a level's leftover
is `parent - sum(children)`, worked out once when the tree is read. That is
what lets a seam be added at any depth without redefining the band above it,
which was the whole reason `geometry` had stayed one number.

- Seams are `flatten`, `repair`, `arcfit`, `engine`, `cull` under geometry,
  and `build_shape`, `hlr`, `loci`, `faces`, `face_polys` inside the engine.
- **The OCP import is 0.783s, paid once per process** by whichever part a
  worker draws first, and unnamed it read as that part's geometry -- 78% of
  it on 3001. It is its own phase now. Read it as a per-batch constant, not a
  per-part one.
- **Legacy rows all sit directly under `render`**, including `decoration`.
  It runs inside `geometry`, but the old accumulator subtracted nested time so
  a legacy `geometry` does not contain it. Nesting it where it runs would read
  that exclusive number as inclusive and take the same tenth off `render`'s
  leftover twice. `stats.LEGACY_PATHS` is where that decision lives.
- Storage did not move. Same `measurements.phases` JSON, keys gain slashes.

**The tree is shallow until r7 lands.** Every row carrying a breakdown when
this was written predates the change, so the wall draws `fill` and `geometry`
as siblings with nothing under them. `brick-icons-1c` relaunched the overnight
occt census as **r7, job `4b141c6f`, at `2d256033`** -- with the
instrumentation, 12h deadline -- so those rows will carry nested paths. They
verified 3001 through `census-batch.sh` on studio first: 14 slash-keyed
phases, and the same measurement r6 gave (missing 0px, extra 14584px, 99th
0.45px), so the geometry is untouched and the two runs stay comparable on
everything but the tree.

**The footprint section counts size on disk, as `du` does** -- the bakes are
303 MB of bytes against 615 MB of blocks, because a 32px thumbnail is mostly
block overhead, and two cells measured differently cannot be compared.
Per-slot render sizes come from `renders.path` in the database rather than a
directory walk, so they count exactly what the wall can reach and follow an
ingest without any change. It is its own route with a five-minute memo:
`/api/corpus/stats` re-polls every few seconds while a census is open and
walking `out/` takes about seven.

**The lab API has no `--reload`.** Anything server-side needs
`pkill -f "brick_icons.lab --port 8792"` and a relaunch before you can see it.
It is a background process, shared with the other sessions here, so say so
when you bounce it.

### The C-grip filled solid because a ring was judged on a column it never reads

`b0c5d85` closes `3820-c-grip-fills-solid`. Every vertex of a `ring`, `disc`
or `edge` sits at local y=0, so the matrix's axis column is not their geometry
-- and `occt.frame()` rejected them anyway when it was not square to the other
two. 3820 caps its grip with two `2-4ring2` whose axis column is 14 degrees off
the ring's own plane, so both fell back to tessellation and the grip filled
solid with no inner rim. Those three kinds are now judged on `u . v` alone and
take `u x v` as the axis. **`cyli` and `con` still fail on any shear** -- there
the axis IS the extrusion direction and a skew one is a real oblique surface
with no exact counterpart.

**It is a wide change, not a narrow one.** 4,479 of the library's 24,591
parts carry at least one such primitive -- 18.2%, a median of 6 each, 43,768
in all. 2,169 of those parts are printed, so 2,310 are in the engine loop
today.

**A/B the change in-process, never against a census render.** Setting
`occt.PLANAR_KINDS = ()` before a render restores `frame()`'s old behavior
exactly, so one process draws the before and another the after -- a worktree
cannot, because the editable install beats `PYTHONPATH` and both sides run
HEAD. Read against its census render, 32054 looked like this fix turned a
near-solid black blob into a clean shaft; A/B'd, it is the same drawing either
way and something else on main had already fixed it. `b0c5d85`'s message
claims it and is wrong. 3820 A/B's exactly as advertised.

**98642 is the second case and it A/B's.** A minifig torso carrying two 3820
hands: with the fix off its left hand is two disconnected slivers floating in
space, with it on the hand is a C-grip ring. Missing area against LDView goes
17,947px in 1 component to 4,905px in 2 -- the component count RISES because
what was one missing blob is now the two thin slivers either side of a drawn
ring. Numbers from `scripts/compare-silhouette-truth.py`'s own scoring at
default stroke widths, so they are comparable to each other and NOT to a
strokeless census row.

**That comparator gates coverage, not tone.** `ours` is the alpha channel
thresholded at 128, so a fill going from one flat gray to a lit band does not
move it at all: 3820 scores missing 0px both with the fix and without, while
the picture is the whole defect. Use it to catch a hole appearing, never to
decide whether a fill got better. Of the 39 affected parts swept, the only one
whose coverage moved is 98642; 4600, 32054, 41334 and 35485 score byte-identical
with the fix armed and disarmed, 41334's 188,496px in 23 components included --
that one is a pre-existing defect this does not touch.

**`2531` and `u9543` have no rejected frames, so this did not touch them**, and
both already drew their open ring correctly. The defect entry grouped them with
3820 and that grouping does not hold -- the discriminator was never openness,
it was the skew axis column.

**The naive golden gate says nothing about an occt change.** `hlr.py` imports
`occt` only inside the `engine == "occt"` branch, and
`test_frozen_hashes_still_reproduce` says in its own comment that it holds the
naive engine still. `BRICK_GOLDENS=1` also passes `--only 3005`, so the fast
mode is one part. Cite `=full`, or cite `tests/test_occt.py`.

### The translucent slot is rendering, and `onto` has four traps in a row

**Mike said do it.** `translucent-occt` over all 8,235 census parts is running
on msb-uai as task `translucent-full`, job `271b71e2`, 6 workers, deadline
18:07. A fetch stream pulls into `renders/translucent-occt/`. `--opacity 0.5`
was already declared by `0faba98`; nothing about the drawing needed writing.

**`0bc8dd3` gave the store the runaway guard it never had.**
`build-render-store.py` built its `Runner` with `isolate=False, mem_gb=0`, so a
store run had `--timeout` and nothing else -- and that is `signal.setitimer`,
whose handler runs only between bytecodes, so an occt render inside one OCP
call ignores it and keeps allocating. It now passes `isolate` and an 8 GB cap,
matching `compare-silhouette-truth.py`. The 300-part trial, run before the fix,
wedged at 295 on 14.4 GB, which is what the guard is for.

**What the slot costs, measured on the 191 trial parts that exist in both
slots.** 2.4x the disk (79 KiB median against 34), and 1.5x the ink (0.231
coverage against 0.158). 11 of 191 land above 0.35 and read as black masses at
thumbnail size. The driver is stud count, not complexity -- every stud has an
anti-stud tube beneath it and translucent draws all of them, so `47405`, a 6x12
wedge plate, goes 0.13 to 0.39 while `63522`, a 2x4 brick, stays perfectly
readable. Whether the slot belongs on the wall or only in a detail view is
undecided.

**Four traps, each of which cost a restart:**

- **`--in brick-icons` is mandatory.** Without it the node has no venv and the
  job exits 127 in under a minute.
- **`out/` does not sync.** A parts list living there is not on the node; scp
  it into `~/.config/onto/work/brick-icons/out/` first.
- **`onto` collapses a space-separated argument list into ONE item.** Passing
  300 part ids inline handed the renderer a single "part" 1,900 characters
  long. Use `--each <list in the tree>` with `'{}'`.
- **Workers sharing one `--log` share one `.inflight` and race on it**, which
  surfaces as `FileNotFoundError: ...inflight` and spurious failures.
  `census-batch.sh`'s header warns about this. Interpolate: `--log
  'out/store/translucent/{}.jsonl'`.

**And a fifth for syncing.** `onto sync --in brick-icons <node>` is required
after a commit or the node runs the old code silently. It refuses while the
node holds job output you have not fetched -- **fetch first; `--force` past
that warning deletes the node's renders.** The fetched renders live under
`renders/`, which is tracked, so 40 MB of them push the sync patch over its
8 MB limit: move them aside before syncing.

### What is not done

- **A translucent slot, both engines. This is the only thing waiting on Mike,
  and the only named item still unstarted.** No such source exists, and **he
  has not said which picture he means**: `--wireframe` (occlusion off, every
  hidden edge drawn, no fills) and `--opacity 0.5` (fills go semi-transparent,
  occlusion still applied) are different drawings. Ask before building.

- **The island cull's 1.2% threshold is bounded on 22 specimens, not on the
  library.** Across 133 candidate islands the rule drops nothing above 1.08% of
  drawn extent and spares nothing below 6.99%, so it is not a marginal call
  there -- but the specimen list is curated for curves and studs, not for small
  features on big parts, which is the shape that would fall through. A
  census-scale answer wants the same counter in `cull_orphan_runs` and a fleet
  run, and the fleet is busy with r7 until 13:15.

- **`3820`'s fix has an obvious next question nobody has asked yet.** `cyli`
  and `con` still reject a skew axis, correctly, because there the axis is the
  extrusion -- but 20 of 10126's cylinders are genuinely oblique and OCCT has
  no exact counterpart for them. Whether an oblique cylinder is worth building
  as a swept surface, or whether tessellating it is the right answer forever,
  is undecided.

- **`10126-unfilled-wedge`** in `tests/goldens/defects.toml`, filed
  naive-only. 20 of 10126's cylinders have a genuinely oblique axis and stay
  tessellated on occt after `b0c5d85`; the other 60 rejected primitives are
  planar and now build exact faces. On occt it draws no white wedge.

- **Badge artwork has one rendering, and it should stay that way.**
  `931b342` put the detail views on `BadgeSwatch`, which is the canvas swatch
  lifted out of `Legend.tsx` and draws through `drawBadge` like the wall does.
  `drawBadge` now takes an optional `label`, stretching the disc to a stadium
  with the word on its own field; no label is the old path exactly. Resist a
  DOM reimplementation of any mark -- the corner-badge lean fixed in `434cc2d`
  existed because the corner path and the strip path had already drifted.

**An agent rebuild silently resets a node's limits.** studio's agent went
`0906.2329` to `0907.0049` mid-evening and lost both `-max-job-time` and
`-max-work-size`: a 6h `--timeout` came back clamped to the 30m default, and
the work quota reverted from 30G to 10G. Nothing says so except the deadline
`onto run` prints, so read it -- 30 minutes means it happened again, and the
fix is `onto install -max-job-time 12h -max-work-size 40G` on the node.

**A pipeline hides the exit code of the thing you care about.**
`bake-thumbs.py | grep | tail` reports *tail's* status, so the bake died
partway through the ldview slot -- 17,371 of 21,797, stale sheets -- and the
run was recorded as exit 0. Write to a log and grep the file.

**Killing a census does not kill what it started.** `onto kill` took r6 off
the job list and left two `compare-silhouette-truth.py` processes alive on
studio, still writing r6 JSONLs -- the orphan case `census-batch.sh`'s
watchdog exists for, except the watchdog dies with the job. Check
`pgrep -f compare-silhouette-truth` on the node rather than trusting the job
list; 1c killed these by hand, and left alone they would have competed with
r7 for cores all night. r6's 8 completed batches are still in
`out/census/occt-r6` and are real measurements at `4905d45`, against r7's 687.

## The census can stop a runaway now, and old failure rows cannot be trusted

`18310b7`. A part that spends its life inside one OCP call -- OCCT's HLR does,
for tens of minutes -- was unstoppable by every cap meant to stop it, and kept
allocating meanwhile. studio reached 24.1 GB of 24.5 GB swap with one render at
4.4 GB after 60 seconds and a batch's renders still alive 36 minutes into a
300s cap.

Three holes, each enough on its own:

- `--timeout` arms `signal.setitimer`, whose handler runs only between
  bytecodes. Sampling the biggest render put 1935 of 1935 samples inside a
  single `cfunction_call` into OCP, under `HLRBRep_Data::NextEdge`. `Runner`
  now has an `isolate` mode: the part renders in a forked child with its own
  process group and the parent kills the **group** -- the group, because
  `occt._unify_survives` forks a grandchild that outlives a kill aimed at its
  parent and keeps rendering as an orphan.
- `census-batch.sh`'s HARD watchdog had never once killed anything. `pgrep`
  returns one pid per line and there are always at least two, so
  `kill -9 "$py"` handed kill every pid as a single argument, which it rejects
  outright into the `|| true`.
- The watchdog also skipped every check when `.inflight` was missing, which is
  exactly the orphan state: no part claimed, renders alive, nobody looking.

**Memory has a cap for the first time, and it cannot be an rlimit.** Darwin
accepts none -- `setrlimit(RLIMIT_AS)` and `setrlimit(RLIMIT_DATA)` both fail
with EINVAL at every value, and `ulimit -d` the same. The parent prices the
child's process group with `ps` and kills it past `--mem-gb`, 4 GB by default
in the census. A healthy part on this corpus peaks under 1 GB.

**So no `ProcessDied` count from before `18310b7` says what it appears to.**
The runaways ran until the node was out of swap and macOS killed whatever it
could reach; the row names whichever part held `.inflight`. Re-derive before
quoting one.

**A census job's `--out` carries the JSONLs and not the renders.** `KEEP`
writes SVGs to `out/census/renders/<engine>` on the NODE, which no `--out`
names, so they stay there and the part reads as `redraw` -- measured, no render
-- forever. 1,039 sticker renders sat on msb-uai that way. The fix is a second
fetch, not a re-render:
`onto fetch msb-uai:brick-icons/out/census/renders/occt out/census/renders/occt`.
Do it as part of every round.

## Superseded, 2026-09-06 late: occt only, and what is unverified

**occt is the engine from now on**, until Mike says otherwise. He said so while
redirecting msb-uai off a naive retry pass. naive is the reference
implementation, not the product; spending a node on a naive bucket spends it on
the engine we are not shipping. Say "on occt" in any report so a naive number is
never mistaken for the current one.

**The sticker census answered its question and is finished.** `census-sticker-occt-r2`
ran the 2,201 stickers occt had not attempted: **1,027 drew, 1,152 failed**.
Ignore any 76% figure -- that was an early slice, and the settled rate is 53%.

**The failures are one thing, and the library says so itself.** A sticker built
on `box5-12.dat` failed 185 of 185, and that primitive's own first line reads
"Box with 5 Faces without Any Edges". Generalized through the subfile tree the
rule is near-exact: of the parts measured, **217 that declare no type-2 or
type-5 line anywhere failed and none drew; every one of the 85 that drew
declares one.** So `OCCT engine produced no edges` is the engine correctly
reporting a part that declared nothing -- not a bug, and not worth chasing part
by part.

- **The fix, if it is wanted, is engine-side and is one change**: where a shape
  has declared faces and an empty authored-edge set, fall back to the silhouette
  of the fused solid. That converts ~200 errors into renders.
- **Seven parts declare an edge and still failed** -- `003497b`, `003497bc01`,
  `004690a`, `163145bc01`, `163555bc01`, `162275dc01`, `164325d`. Six of the
  seven are *formed* stickers or their flat siblings. That is the class worth
  looking at; the 217 are not.
- **Minifig torsos are not the problem** -- they are in the drawn column. The
  failures are flat: plain N x M rectangles, round discs, flags.
- Reference photos: a sticker id is its sheet number plus a letter, and the
  sheet is the catalog entry, whose Rebrickable name gives the set. e.g.
  `003497b` -> sheet `003497` -> set `271-1`.

**Stickers file under `census-occt`, not a slot of their own.** Mike reversed an
earlier decision here; `234100c` removed the `census-sticker-*` sources again.
`census_source` falls back to `census-<engine>` for any tree naming no declared
facet, so dropping the sources was the whole change and `out/census-sticker`
files itself correctly.

**The wall's ground is one color at every rung, and bakes carry no ground.**
`thumbs.GROUND` is `(0, 0, 0, 0)` and the wall paints `thumbGround()` under the
sheet, the loose PNG and the live SVG alike (`3e9cfdd`, `4b2fa8c`). Before that
each rung answered "what is behind this cell?" differently and a cell jumped
`#ffffff` to `#c9cbcf` on one wheel notch.

- **A ground has to clear the fills, not just the page.** An OCCT lit face is
  `#cccccc`; `--wzl-gray-200` is `#c9cbcf`, which is 1.01:1 against it and hid
  13% of all drawn ink across 400 parts -- two thirds of it on a pale part. The
  ground is white, and it lives in `--corpus-thumb-ground`, which the Lightbox
  already used. Measure any candidate against `#cccccc`, never only against the
  page background.

- **Changing it is a repaint, not a rebake.** A rebake is only forced by
  clearing `out/thumbs/<slot>`, because the sha check skips a part whose render
  has not changed -- so a stale slot reads as *unchanged* rather than broken.
  All five vector slots were re-baked (26k parts, 569 s).

- **A corner badge centers on its caption's ink**, not on its own radius
  (`434cc2d`). `badgeGeometry` keeps `inset` for across the cell and gains
  `rise`/`fall` for down it. The lean was 0.21 of the type size: 0.13 from
  `radius + pad`, and `CAPTION_INK_RISE` = 0.0823 because canvas sets a caption
  on `middle` and Oswald's ink centers above that anchor.

**The `ldview` slot is back, and why it vanished** (`ae2464e`). Re-encoding it
to WebP made every one of its files invisible to the rebuild, which indexed
`(".svg", ".png")` and nothing else -- so it wrote no rows, and the picker lists
whatever `renders` has rows for. The list is `db.RENDER_SUFFIXES` now.
`thumbs.bake_part` gained the raster branch that had to exist beside it: PIL
opens a raster, resvg keeps the vector path, and that is why ldview had no
thumbnails before.

**The slot is now the whole library** (`75d6a31`). 21,797 renders -- every
in-scope part; stickers and the `|` category stay out. studio drew the 17,901
missing ones in 26 minutes under `scripts/ldview-batch.py`, which takes a
comma-separated batch so onto's `--each` can own the pool, and skips a part
whose `.webp` is already there so it resumes. Two things it had to fix first:
`process_one` wrote LDView's PNG into `renders/ldview/` before converting it,
which `db.rebuild` would index as the render, and which raced a fleet fetch
listing the slot -- five rounds in a row 500'd on `lstat ... no such file` and
15,000 renders sat on the node for half an hour. The PNG goes to a temp dir
now. `bake-thumbs.py` also died on the first zero-byte file an interrupted
fetch left behind, abandoning the twenty thousand parts after it; it logs
UNREADABLE and continues.

**Both pages poll now** (`bd5c6de`, `0f66367`). The wall fetched its slot list
once at mount, so a page open across an ingest showed a menu that no longer
matched the store. The dashboard stopped reading whenever no run was open, on
the reasoning that the database is static between runs -- it is not, and the
only way to see an ingest or a rebake was a reload, which redraws every chart.

**The Google Fonts link is gone from all three lab pages**, and `thumbFontReady()`
in `main.tsx` stays. Labkit's `oswald-latin-variable.woff2` (200-700) serves both
weights and the stylesheet's ten faces never loaded. **The gate is not dead
weight with it:** held the woff2 back 12 s and zoomed to captions, and without
the gate they draw in the fallback face and **never repaint** -- a caption keeps
whatever face was loaded when it was drawn. Removing the link rests on labkit
shipping that face, so re-check it before bumping `^1.4.0`, not after.

**The wall opens far below every decoration threshold.** It refits to about
6.5 px per cell; glyphs need 22, badges 56, captions 110, and the sprite-to-
vector swap lands between 151 and 166. So an empty-looking wall is the default
view, not a regression. One wheel notch is 1.1x regardless of `deltaY` and is
anchored at the cursor -- which is how to crop the same cell at two zooms. About
24 notches from refit to badges, 30 to captions, 34 to vector. `vectorGround()`
caches on first call, so judge grounds after a full reload, never over HMR.

**Two traps that cost real time tonight, both fixed, both worth knowing:**

- **A stale lab server 500s every DB route.** `db.connect` raises when the file
  is at a higher schema than the code, so a server started before a schema bump
  fails every request. Restart it after a bump.
- **`bake-thumbs.py` fed every render to resvg**, which reads SVG only. LDView
  emits PNG, so one ldview row killed the whole bake with "provided data has not
  an UTF-8 encoding" -- which reads like a corrupt file rather than the wrong
  kind of one. It skips rasters now.

**Sharing this tree:** `brick-icons-4b`, `brick-icons-b8`, `brick-icons-40` and
`Status icon for thumbnails` are all in this same directory. Stage explicit
paths, never `git add -A`; their uncommitted work in `paint.ts`, `Wall.tsx`,
`params.ts` and the stats files is not yours. `tests/goldens/part-status.toml`
and `wall-census-naive.png` sit *staged* in the shared index and are someone
else's -- keep them out of your commits.

## Finished, badly: the naive retry passes, and two slots that do not exist yet

**Both naive retry passes are over and neither is worth re-reading.**
`census-white-naive-r3` was cancelled and pruned; `-r4` timed out after 2h12m
of CPU with its batch counter still at `0/134` -- every logged item reads
`FAILED TimeoutError: exceeded 300.0s`. msb-uai is idle, carrying one stale
record (`475fecdf`, "the supervisor is gone and wrote no result") from a pass
that was scoring stickers at a false `missing 0px / extra 0px`. Both passes
ran naive, against the occt-only decision at the top of this file.

studio's `census-white-occt-r3` reached 19 of 59 batches and is also gone. Run
the next round through the `census-round` skill, which holds the traps.

**Do not quote a ProcessDied count from any run before `18310b7`.** The
watchdog that produced those rows had never killed anything -- `pgrep` returns
one pid per line and `kill -9 "$py"` handed kill every pid as a single
argument, which it rejects outright into the `|| true`. So the runaways were
never stopped, the node ran out of swap, and macOS killed whatever it could
reach: a `ProcessDied` row names whichever part happened to be holding
`.inflight`, not the part at fault. That includes the claim this section used
to make -- that 149 of occt's remaining 698 rows are ProcessDied and 57 of
those are the segfault `00f4e32` survives. **The 57 has to be re-derived from
a post-`18310b7` run before it means anything.**

**Two slots Mike asked for, neither built:**

- **`ldview`** is already in `db.SOURCES` and `_CANONICAL`, and the wall builds
  its slot list from `renders` rows, so nothing needs designing -- the store
  simply has no ldview rows. One bug is in the way: `build-render-store.py`
  hardcodes `dest = renders/<source>/<part>.svg`, and LDView emits a raster.
- **transparent, both engines** -- no such source exists. It needs
  `translucent-naive`/`translucent-occt` in `SOURCES` and `_CANONICAL`, and
  **Mike has not said which picture he means**: `--wireframe` (occlusion off,
  every hidden edge drawn, no fills) and `--opacity 0.5` (fills go
  semi-transparent, occlusion still applied) are different drawings. Ask before
  building.

**Filed but uncommitted:** `3820-c-grip-fills-solid` and `10126-unfilled-wedge`
in `tests/goldens/defects.toml`, beside Mike's own uncommitted
`3484-occt-handle-missing-arcs-extra`. 3820 is fixed by `b0c5d85` and the
reading below was wrong: the failing case was never the open ring, it was a
skew axis column on a planar primitive -- see the section on it above.

**Landed today:** `f224fdf` + `b86e88c` (TriangleOccluder vectorized, then
culled by the ray chunk's screen box -- 3.8x at 304 tris to 21.7x at 4,240,
interleaved), `a2d43dc` (`measurements.build`, schema 5), `533c47a` (the
`census-round` skill), `00f4e32` (the UnifySameDomain segfault guard). Every
one gated byte-identical on the 22 specimens.

**Measurement discipline, learned the hard way today:** never quote a speedup
from sequential runs -- alternate the order and take the min per side -- and
`measurements.secs` is the whole oracle pass, not the geometry phase, so a
geometry speedup does not divide into it. `2613aeb` added
`measurements.phases`, which makes that unmixable.


On **`main`**, pushed through `6a780c5`, with the goldens re-freeze, its
crash fix, and the whole `labkit/annotations-arc-5` arc committed on top and
unpushed. A plain `pytest`
skips the drift tests, and `BRICK_GOLDENS=1` renders only `3005` — neither is
verification; only `BRICK_GOLDENS=full` (~18 min) is.

**START HERE: the goldens are re-frozen and `BRICK_GOLDENS=full` is green**
(16 passed, 17m31s). The drift `fbfda92` caused is re-measured below, against
BOTH halves of that commit this time.

Re-freezing it turned up a hard crash, now fixed: `6589` at
`--shade-style flat3` died with a GEOS side location conflict on the NAIVE
engine, so the part drew nothing at all. One of its merged fill elements is a
valid but sub-0.04 px spike, and `_donate_escaped_spurs` buffers each
element's own BOUNDARY by 0.02 to find the seam — which self-intersects at
such a spike's tip and hands GEOS an invalid operand. The element's thinness
is not something that pass may assume away; it repairs the band now. Gated by
`test_6589_spike_sliver_does_not_break_the_spur_donation`. Blast radius
measured at byte level: of the 23 `outline-flat3` cases, the repair changes
`6589`'s hash and nothing else.

    .venv/bin/python scripts/freeze-goldens.py --out /tmp/new
    .venv/bin/python scripts/compare-goldens.py /tmp/new --out report.md

**Run the freeze one case at a time.** A whole-corpus `freeze-goldens.py` was
killed at 35/52 twice; the cause is now known — the OTHER session was
rendering `3649` at the same moment, and two of those at once is what the
machine will not carry. A `--only <case>` loop over the 52 ids finished every
time, and prints per-case timings worth keeping (`outline-flat3__3649` 330s,
`4740p03` 114s, `outline__3649` 230s; everything else under 25s).

## The wall, 2026-09-06 evening: what landed and what Mike still owes an answer on

All merged to `main`; `git log --oneline @{u}..HEAD` shows the unpushed run.
Nothing here is in flight -- this section exists for the decisions, which are
not recoverable from the diff.

**Stickers are their own thing now.** `6881734` stops `tags_for` calling a
sticker printed: `partindex.printed` reads "pattern" *or* "sticker" out of the
description, so all 2,701 sticker parts wore the printed badge. The LDraw
category wins where it applies, and the two never both show.

**The sticker badge is `239406c`.** The disc *is* the sticker and its corner
lifts off the print. Three decisions in it that the code cannot tell you:

- **POLICE, not flames, M:Tron, skull or a shield** -- Mike picked it off a
  candidate sheet. `flames` (the fire emblem off sticker `004659a`) is kept as
  the alternative and `lab/sticker-candidates.html` compares the two; swapping
  `mark` on the badge in `paint.ts` is the whole change. The other fifteen
  candidates were deleted.
- **Outlines, never a webfont.** Mike's call, and it is the right one: no font
  to ship, no race between first paint and the font landing, no fallback face
  setting the word at another width.
- **Navy, not the shared property field**, because a sticker is a thing you
  apply rather than a fact about the moulding.

**Centering a badge face means centering its drawn box.** Not its area
centroid, and never the ink left showing after the fold. I got this wrong twice
and Mike caught both: correcting for what the flap covers put POLICE a fifth of
a unit right of where it belonged. A traced face is already centered by the
trace -- all six measured [-0.002, -0.002] -- so only type needs a nudge,
because a baseline is not the cap-height center. `FACE_NUDGE` carries the
measurement and its reasoning.

**Trace artwork, do not draw it from memory.** The M:Tron, Blacktron and
Exploriens marks I first drew were wrong, and Mike said so. `brick-icons decal
<part>` unwraps a printed part's decoration flat, and the library has the real
thing: `3068bp68` (M:Tron), `2408p01` (Blacktron II), `2335p05` (Jolly Roger),
`168135h` (the City fire shield), `003238c` (a Maltese cross), `3004p21` (the
police star badge on sheet 22637), `004659a` (the fire emblem). Union the
colored subpaths, weld hairlines with a dilate/erode, simplify, normalize on
the bounding box.

**Answered, in `6467668`: the legend counts the wall, and the tags count the
menu.** It used to count all 24,591 library parts against a wall showing
23,432, so "19,928 unknown" was mostly the 13,083 printed parts the census
never targets. The state rows follow `shown` now.

The tag rows could not, and that was the whole difficulty: they are the control
that applies the filter, so over `shown` they read 0 for every tag but the one
picked, and the list you choose the next tag from destroys its own information.
They count over `untagged` -- the wall narrowed by everything *except* the tag
picks. Two tags picked will not sum to the wall's total; that is what it costs
to keep the row a menu, and the sidebar's category counts already pay it
(`CorpusWall.tsx`, "a facet's own checkbox must not zero out the moment it is
cleared").

**Answered: better part-year data. No source beats the one we have; what we
have is being read badly.** Sources first:

- **Brick Architect publishes no export**, and its terms prohibit reuse without
  permission. Its year ranges come from *Brickset*, and Tom Alphin says on the
  site that they get less accurate before the 1990s and that he intended to
  switch to Rebrickable. He gives `3005` as his worked example of a wrong start
  year; ours already reads 1954-2026.
- **Brickset's API has no parts methods** -- sets, minifigs, collections,
  themes. The year data Brick Architect takes from it is not reachable per part.
- **BrickLink's API returns `year_released`** per catalog item and only that:
  no end year, OAuth1 with a registered consumer and an IP whitelist, ~5k calls
  a day. Its bulk catalog download sits behind a login, so whether the parts
  file carries a year is unchecked -- that one needs Mike's account.
- **Rebrickable's API takes an `ldraw_id` filter**, which the dumps do not
  expose. That is from its own OpenAPI schema
  (`/api/v3/swagger/?format=openapi`), not from the docs prose. Whether the part
  object also carries `year_from`/`year_to` is unverified -- the schema declares
  no response models and the site is behind Cloudflare. A free key settles it in
  one request.

**The gap is ours.** 9,269 of 24,591 parts (38%) have years. Of the 15,322
without, 7,593 are LDraw constructs no catalog will ever hold: 3,306 shadow
parts, 2,701 stickers, 1,127 composites, 459 aliases. Two routes close much of
the rest, both from dumps, no key:

- **`elements.csv`'s `design_id` column** maps LEGO design numbers -- what LDraw
  uses for modern parts -- onto Rebrickable part numbers. **+2,020 parts**, to
  11,289 (46%). It is not in `DUMPS` yet; one more download.
- **`part_relationships`' mould rows (`M`)**, which the script already pulls for
  successors. Rebrickable splits early moulds off under their own numbers, so a
  1958 set is inventoried against `3001a`, not `3001` -- which is why our Brick
  2x4 reads 1979. Unioning a part's mould family moves the start year earlier on
  **1,610 parts** and the end year later on 850: `3001` 1979->1954, `3003`
  1985->1954, `3068b` 1975->1965. The closure is well behaved -- every family is
  variants of one part, the largest is 9.

**Decided against: the mould union.** Mike left the call to me. It is right when
the LDraw file is the generic part and wrong when it is one specific mould, and
no rule separates the two. Three were tried and all fail on parts whose names
say outright that they are late moulds:

- *union everything* -- gives `6947`, the vented-stud minifig head, 1975.
- *only where LDraw does not model the siblings* -- holds back `3001`, the one
  case that most obviously should union.
- *only plain numeric ids*, and *only the shortest name in the family* -- both
  hand `50665`, "Helmet Classic, New Mold 2019", a start year of 1979, and
  `3556`, "Brick 2 x 4 without Cross Supports [Modern]", 1954.

Right on maybe three parts (`3001`, `3002`, `3003` -> 1954), wrong on hundreds,
and the failure is silent: a modern mould backdated forty years is exactly what
`retired` and `obscure` key off. So `year_from` keeps a definition that is
consistent and explainable -- *the first year Rebrickable inventories this exact
mould number* -- which is why our Brick 2x4 reads 1979 and not 1958. If those
few matter, a hand-curated exception list is the honest fix, not an inferred
rule.

**All of this is built and loaded** -- `scripts/fetch-part-years.py` carries the
routes, and `part_years` went from 9,269 rows to **19,033 of 24,591 (38% ->
77%)**: 5,051 exact, 4,218 base, 2,020 design, 1,158 sheet, 6,586 keywords.
Printed parts reach 95%, stickers 95%, plain 61%. The CSV under
`tests/goldens/` is the durable form and `db.rebuild` reloads it, so the census
ingest's next swap of `corpus.db` keeps it rather than clobbering it.

**Stickers are not unfixable -- that claim was wrong.** Two routes give 2,680 of
2,810 sticker parts a year:

- **The sheet number.** Strip a sticker's trailing letter and the sheet is in
  the Rebrickable catalog (`003381` is "Sticker Sheet for Set 663-1"), with set
  inventories behind it. Worth 795 parts, plus 16 more from parsing the set out
  of the sheet's own name.
- **LDraw's `!KEYWORDS` line names the sets.** `003238a` carries
  `Castle, part 3846, set 375-2, set 6075-2`; those numbers go straight into
  `sets.csv`. Never touched before, and it is in `vendor/ldraw` already.

**`!KEYWORDS` is a fallback source only, and the gate is not negotiable.**
Against the years we already trust it is poor in general -- 3,865 parts overlap,
median 10 years off -- because a common part's keywords name two illustrative
sets out of thousands, not the earliest. Accuracy is a clean function of how
many sets the part is in:

| sets the part is in | exact | median error |
|---|---|---|
| 1-2 | 49% | 1 yr |
| 3-10 | 46% | 1 yr |
| 11-100 | 18% | 4 yr |
| >100 | 1% | 14 yr |

Stickers sit at the top of that table and hit **95% exact** against the 691 with
a sheet-derived year to check against. So use `!KEYWORDS` only where the
inventories give nothing -- a part absent from every inventory is by
construction a part in few sets, the regime where keywords are good. Mixing it
into parts that already have inventory years would make them worse. The route is labelled in
`part_years.matched`, and `cells.sets_for` returns None for an estimated row so
the wall cannot read a popularity out of it. That guard is load-bearing:
`part_years.sets` is `NOT NULL DEFAULT 0` and `tags_for` calls `sets <= 2`
obscure, so serving the 0 tagged all 6,586 estimates obscure -- 8,517 against a
true 1,931. Making the column nullable would have meant a schema bump, and one
of those had just 500'd the lab for every session; suppressing at the read is
the same answer without it.

**occt renders decals now** (`4b80035`, gated by `cd7ce2c`). Mike was asked
whether occt should do this corpus-wide and answered that there is no reason
not to; the question was badly framed. The real constraint was only timing --
do not change the engine under a running census. The gate is the same test
`partindex` classifies the corpus with, because color-other-than-16 is not a
print signal: every sub-part of an assembly carries its own, and running the
carrier search over `604ac01` cost 6.8s of its 8.8s geometry phase to draw
decoration it does not have.

**Also landed:** `f5538b1` hovering a legend tag dims the wall like a hovered
state; `d19f4e4` params moved into the sidebar and the part card leads with its
render; `259ea5f` params rows are full-width (a row's label and readout share
one `nowrap` flex line whose text is an *anonymous* item, so a long label
cannot be shrunk from outside the component); `78aea11` a legend toggle in the
topbar and cmd-0 to refit; `d2b9fb2` a zoom keeps the card the pointer is over,
and a jump lands centered at half the viewport height.

**Staging in this tree needs care.** Three or four sessions share it. My
`paint.ts` change had to be staged apart from another session's in-flight
badges/captions work: build your hunks on top of `git show HEAD:<file>`, then
`git hash-object -w` and `git update-index --cacheinfo 100644,<blob>,<path>`.
Their `paint.test.ts` failures are theirs; the corpus suite is otherwise green.

## Decals on the occt path: DONE, and this section used to say otherwise

`4b80035` built it. `occt._with_decoration` pulls the colored source triangles
alongside OCCT's own faces and hands both to `shade.unwrap_decoration`, which
finds the carrier among OCCT's planes — a sewn solid stamps every face 16, so
the print is not in the solid and never could be.

Re-measured 2026-09-07: `20308p02` emits the same palette on both engines
(`#b40000`, `#f6a9bb`, `#720012` and the rest, same counts), and the two SVGs
draw the pig's eyes and snout identically. `3068bp00`, `3040bp08`, `4740p03`,
`3941p01` and `3942bp01` agree too. Decoration is no longer a reason the flag
cannot flip.

**Read a printed part's SVG, never its `.gray.png`.** Under `--shading
outline` the PNG modes go through `process.draw_segments` /
`process.segments_mono`, which take strokes and contour rings and no `fills` —
`fill_ops` is called only inside the SVG branch of `cli.process_one`. So
`--shade-style flat3 --format png` silently produces line art with no shading
and no print, on **both** engines. An engine A/B run on those rasters reads as
agreement no matter how far the fills have diverged.

## In flight: the colour tint — branch `corpus-colors`, green, waiting to land

Worktree `.claude/worktrees/cgc`. Two commits on top of `main`: the colour count
itself and a merge of `main`. **Complete and green** — 645 lab tests, 70 Python
(`test_lab_cells.py` + `test_db.py`), `tsc` clean, `npm run build` emits both
entries.

It is a pure fast-forward (`git merge --ff-only corpus-colors`), blocked only by
an uncommitted `lab/src/corpus/paint.test.ts` in the main checkout. Nothing to
resolve; it lands the moment that file is committed.

**Landing it requires restarting the lab server on 8792.** `SCHEMA_VERSION` goes
3 → 4 and `db.py` has no ALTER path, so the ingest loop's next 15-minute tick
rebuilds `corpus.db` at schema 4 under a server still holding schema 3 — the
"no such column" blank wall. This is the case the note above already warns about.

What it does: extends `part_facts()` in `scripts/fetch-part-years.py` to collect
distinct `color_id` in the pass it already makes over `inventory_parts`, adds one
`colors` column to `part_years`, serves it from `cells.py`, and adds a fourth
`TINT_MODES` entry. No second table and no second importer — the abandoned
`corpus-grouping` branch's `part_facts`/`part_colors` tables are exactly what
this avoids.

**`tests/goldens/part-years.csv` is regenerated in the same commit as the loader
change, deliberately.** `import_part_years` reads it by name, so a loader that
expects `colors` against an un-regenerated golden dies with a bare `KeyError`
inside `rebuild`, which reads as a corrupt database. The loader reads
`int(r["colors"])` straight, with no tolerant default: zero colours is not a
fact about any part, so a default would put all 9,269 parts on the ramp's bottom
shade and render a missing column as a finding.

**The ramp constant was measured twice and the first number was wrong.**
`MAX_LOG_COLORS = Math.log10(80)`, over the golden's 9,269 dated parts: median 9,
p90 63, max 80. An earlier measurement said median 4 / max 81 because it joined
only the 5,051 `exact` matches and missed the 4,218 `base` ones. Log beats linear
either way — 25% of the wall in the bottom two of eight shades against 62% — but
recompute from the golden, not from `inventory_parts` directly, if the ceiling
ever needs revisiting.

### Dead, safe to delete

`corpus-grouping` at `349fc8e` — the original 19-commit branch. Its Rebrickable
backend duplicated `part_years` and does not land; the useful half was ported and
is on `main` as of `a3f5b90`. Worktrees `.claude/worktrees/corpus-grouping` and
`cg2` are disposable.

## Next: render performance

Agreed in conversation, nothing written down elsewhere. A lab render is slow
enough to be the thing that limits working in it, and the census measured why:
a naive render's median is 12s, its 90th percentile 76s, its worst 695s; occt's
median is 22s. Three things to do, in order:

1. **Run renders in a `ProcessPoolExecutor`, not threads.** `lab/runner.py`
   calls `cli.process_one` in the API server's own process, on a daemon thread
   per job, so two renders take turns on the GIL and both hold up the server
   that is also serving artifacts.
2. **Cancel a superseded render.** Change the config again and the old render
   runs to completion, and its result is thrown away.
3. **Serve a known part from `renders/` once the store exists**, so opening one
   is a file read.

**Stop the census before measuring any of this** — `pkill -f
compare-silhouette` — or you are timing eight of your own render processes
fighting for eight performance cores.

**Threading one render's booleans: tried, byte-safe, worth nothing.** GEOS
releases the GIL (a synthetic boolean load scales 4.8x over 8 threads), so the
obvious move is to thread the independent maps in `fill_ops` — the impostor
cuts in `_refine_order_clips.apply` and the per-group merge unions. Output was
byte-identical on six parts and the speed was 0.99-1.02x on every one of them.
The reason is granularity: on `0901`, 224 of 227 of those maps carry exactly
ONE item, and those single-item maps hold 56.5s of its 116s. The fill stage is
a chain of a few hundred large serial booleans, so spending a second core means
splitting one boolean — canvas tiling, which brings back the T-junction seams
the coplanar plane-merge exists to remove. Reverted; don't re-propose it
without a plan for that.

**The parallelism that is really there is in the hidden-line stage**, and it
wants vectorizing before it wants cores: `hlr.visible_segments` is 67% of
`66790`'s render and per-segment independent, but it is Python-level numpy —
895,872 `np.cross` calls with 5.4M axis-normalization calls under them — so it
holds the GIL throughout and most of that time is dispatch, not arithmetic.

**Trap from the same experiment:** threading the per-face intersection sweep
that builds `near` changed the SVG bytes. Not slower — wrong. Whatever the
mechanism, a shapely call threaded over geometry another thread also touches
has to be proved byte-identical before it is believed.

## In flight: the white census facet, third pass -- the 300s cap

Both engines are running at a **300s per-part cap, up from 120s**, `HARD=600`:
`census-white-occt-r2` (93af72b4, studio, 8 workers, 959 parts, launched 17:06,
deadline 05:06) and `census-white-naive-r2` (ed49e9f8, msb-uai, 10 workers,
1,909 parts, launched 18:08, deadline 06:08). An `onto fetch --stream` per task
collects into `out/census-white-{occt,naive}/`. **The ingest loop belongs to
the Database web UI session** -- one loop, not two.

**A retry pass needs its own directory.** A batch's JSONL is named for its
first part, so a retry batch beginning with a part that also began a batch of
an earlier pass appends to that pass's file -- and `--skip-done` then reads its
120s TimeoutError rows as done and skips exactly the parts being retried. 15 of
occt's first 37 batches started non-empty this way and one was skipped whole.
naive writes to `out/census-white/r2` for that reason; `db.rebuild` rglobs, so
a subdirectory is still indexed, and `KEEP` still points at the shared
`out/census-white/renders`. occt's running pass predates the finding and keeps
the flaw -- harmless, because a skipped part keeps its old error row and so
comes back in the next coverage list.

**`onto sync` a node while it runs a job is refused**, with a 409: sync takes
the tree lock and a running job holds it. It is a refusal, not a loss --
`out/` is gitignored and the reset's clean is not `-x`, so census output and
the rsync'd batch lists survive a sync either way. `onto sync` also wants
`--ref origin/main` here, because the branch has no upstream and onto cannot
otherwise name a commit the node is known to have.

studio was synced before `273a6dd`, so **occt's worker labels still show the
batch's first part**; msb-uai has it and naive's name the part in hand. Same
for onto's own `22/-117` progress arithmetic, fixed in `b137f50`: a running
job keeps the supervisor it launched with.

**`--env PATH` is not optional.** The agent's PATH has no `~/.local/bin`, so
`resvg` is missing and every part fails `FileNotFoundError` in about a second
-- fast enough to write a few hundred error rows before anyone looks, and
`--skip-done` then skips those parts for good. A launch without it is worse
than one that crashes.

Parts that only ever timed out at 120s are finishing at 300s, so the cap was
the binding constraint and not a rendering fault.

**onto's automatic pool sizing gets this job wrong.** It divides free memory
by the task's recorded peak -- 18.3G, which was the whole 8-worker job, not
one part -- and hands out one worker. Pass `--workers` explicitly; 8 on studio
and 10 on msb-uai are what earlier passes ran at, at ~2.3G each.

`649bdba` -- **a part the batch attempted now always gets a row.** The
watchdog kill left the part named in `<jsonl>.inflight` and nowhere else, to
be buried only on the way into a re-run of that same batch; where onto ordered
none, the part was in no census at all -- not drawn, not failed, just absent,
and so invisible to the coverage list the next run is built from. A segfault
was the same hole one level up, losing every part after the killer.
`census-batch.sh` buries the in-flight part itself and resumes the batch;
`compare-silhouette-truth.py --bury` writes that row with the facet's own
engine/angle/style/strokes. 120 naive and 147 occt parts went missing this way.

**Read a facet by `source`, never by `engine`** -- an engine's two facets are
both "naive". `census-coverage.py --facet` does; its default oracle path still
reads by engine and counts a white measurement as the oracle's.

Two earlier bugs of that same shape, both fixed: `e60f811` (renders --
`config_key` comes from the source alone, so a second facet indexed under
`census-<engine>` replaced the oracle's rows) and `a1295f5` (measurements --
`census-white-*` sorts last, won `MAX(run_id)`, and every oracle cell on the
wall showed white figures; **schema 2**, so restart any lab server after the
next rebuild).

**Do not read a white row against an oracle row.** Strokes put a ~1px band
outside the fill boundary everywhere, moving `extra_dist_px` 99th from ~0.45px
to ~1.01px on every part. The facet is worth having for its drawings.

**Not built:** the wall wants a third border color for a part that renders
correctly but slowly, distinct from one that fails. `measurements.secs`
already carries what it needs; nothing reads it for status yet.

## Superseded: the first white census pass


Ran 2026-09-06 01:19-09:19 on both nodes, **merged to `main`**, both jobs
stopped by their 8h deadline rather than by finishing.

| | naive (msb-uai) | occt (studio) |
|---|---|---|
| parts reached | 5,670 of 8,235 | 6,661 of 8,235 |
| measured | 4,378 | 5,982 |
| errored | 1,294 (1,285 timeouts) | 679 (529 timeouts, 125 ProcessDied) |
| in `corpus.db` | 4,393 renders | 5,997 renders |

Everything is collected, ingested and baked; the wall draws both slots.
**naive timed out at more than twice occt's rate** against the same 120s cap,
which is the opposite of the strokeless facet and worth a look before
budgeting another run.

To finish the corpus, relaunch the same two jobs. `--skip-done` reads the
JSONL already in `out/census-white-*`, so a second run costs only what is
left, and the batch lists still have to be rsync'd to each node -- `--each`
reads its list in the tree and `out/` is gitignored:

    rsync -a out/census-white/{naive,occt}-batches.txt \
      <node>.local:~/.config/onto/work/brick-icons/out/census-white/

`scripts/census-ingest.sh 900` rebuilds corpus.db on an interval while it
runs, and `scripts/bake-thumbs.py --source census-white-naive` afterwards is
what puts new parts on the wall -- indexing alone does not, and it is
idempotent by render sha so it only costs the new ones.

**These numbers are not comparable to `out/census`.** Strokes add a ~1px band
outside the fill boundary everywhere, moving `extra_dist_px` 99th from
~0.45px to ~1.01px on every part. The facet is worth having for its drawings,
not its measurements.

## In flight: the library-scale silhouette census, now on `studio`

Eight detached shards (4 naive, 4 occt) run
`scripts/compare-silhouette-truth.py` over `out/census/parts.txt` — 8,235
unprinted library parts, the corpus the 21-part `unprinted` list samples.
`scripts/run-census.sh` starts or resumes it; every shard streams JSONL and
skips what it already has. Read progress with `scripts/census-report.py`,
which prints coverage per engine and ranks the worst parts.

**It runs on `studio` now, not here**, in the onto working tree at
`~/.config/onto/work/brick-icons` — the rows this machine had collected were
copied there first, so the shards resumed rather than restarted. Bring results
back with `onto fetch studio:brick-icons/out/census .` and merge; a shard
writes only its own file, so nothing conflicts.

**Studio reproduces this machine's numbers exactly** — `3001` gives 14590
extra px on naive and 14584 on occt on both — so its rows merge with the ones
already collected. That is not free, and two things buy it:

- **`resvg` must be the 0.47.0 the lock pins.** Brew now serves 0.48.1, and
  resvg's antialiasing *is* the comparison reference, so a node on the wrong
  one produces plausible numbers that mean something different. Studio has the
  0.47.0 binary copied over and sha256-verified, at `~/.local/bin/resvg`.
- **LDraw must be the same snapshot.** `complete.zip` is rolling, so fetching
  it on a new machine gets a different library. Studio's copy was rsynced from
  here and verified with the manifest command in `scripts/external-deps.lock`:
  36603 files, `5f855079…`.

**Two dependencies are missing from `pyproject.toml`.** The census script
imports `scipy`, which nothing declares, and the `occt` engine needs the
`cadquery` extra on top of `occt`. A fresh checkout installing `.[occt]` gets
neither, and fails at the first import. Worth fixing in `pyproject.toml`
rather than remembering.

What it is for: the oracle needs no golden and no eye, so it answers at
library scale the two questions 21 parts cannot — which parts either engine
omits real geometry from, and how far `occt`'s silhouette sits from the part's
own polygons, which is the open blocker on making it the default. On the parts
both engines have measured, **naive omits real geometry more often than occt**
(roughly 11% against 5%), though occt's failures are far larger when they land.

**occt segfaults on some parts, and it has killed its shards three times.**
The crash reports are all one frame — `SIGSEGV` in
`ShapeUpgrade_UnifySameDomain::IntUnifyFaces`, OCCT's own C++ — and `92738`
under `--engine occt` reproduces it on demand, exit 139. Five parts are known
to do it: `92738`, `u9236c03`, `76110p01`, `u9105p01c04`, `47326p01`. A native crash writes
no row, so each shard now names the part it is rendering in `<jsonl>.inflight`
and records it as `ProcessDied` on the way back in — which means **a shard that
dies needs one restart to get past its killer, and a second run to make
progress.**

`scripts/census-shard.sh` does that restarting, and every shard runs under it
now — `run-census.sh` launches shards but does not watch them, so one crash
costs that shard the rest of the night.

**The whole census is one onto job**, `scripts/census-run.sh`, which starts
every shard in parallel and waits. It is one job rather than eight because
onto locks a working tree to a single job, and that is the right shape: the
census is one workload on one tree. `onto jobs` shows its CPU and peak group
RSS; `onto logs -f <id>` follows every shard interleaved, with a progress line
joining them every five minutes.

**Shards are split per engine, not shared.** The two engines run at different
rates and are rarely the same distance through, so a shared split spends half
the machine on whichever one is nearly done. `scripts/census-reshard.py
<engine> <n>` re-splits just that engine's unfinished parts into n fresh
shards, leaving out anything already recorded in any of its JSONL files, so no
work is repeated and old files stay as the record. Studio runs 3 naive and 5
occt against its 8 performance cores — naive had 22 core-hours left against
occt's 102, and occt is the blocker.

**The census's renders are NOT the store's renders, and they cannot be
promoted into it.** `--keep` saves what the oracle drew, and the oracle draws
strokeless on purpose — `--line-width 0 --silhouette-width 0`, so fills carry
the silhouette with no stroke overhang to subtract from the comparison. The
store's canonical render is the ordinary stroked drawing `db.canonical_argv`
names. Copying one into the other puts a file under a key describing a
different drawing; it was tried and backed out. `out/census/renders` is
evidence for a finding, to be looked at beside the numbers. The store gets
filled by its own job, which is part 2 of the database plan.

**The per-part cap is 120s, it does not bound wall clock, and the tail is
worse than it looks.** SIGALRM lands between Python bytecodes, so a part stuck
inside OCCT or shapely runs straight past the cap — one measured 695s against
it. Worse, when the shards were stopped on 2026-09-04 at 23:18, **all eight had
written nothing since 22:57**: twenty-one minutes of eight-way render time with
no row to show for it, and no timeout fired in any of them. The four occt
shards were on `4480c04`, `7757`, `85834` and `12890`. Treat a cap as a
throughput hint, not a guarantee, and read progress from the log's mtime rather
than from the fact that processes are alive.

About a fifth of the corpus hits the cap, burning roughly 40% of the CPU on
parts that record nothing but "too slow". A `TimeoutError` row is a
rendering-cost finding, not a defect.

## The corpus database

`docs/superpowers/specs/2026-09-04-corpus-database-design.md` is the design and
`docs/superpowers/plans/2026-09-04-corpus-database.md` the plan, and part 2 —
the job that fills the store — has its own plan at
`docs/superpowers/plans/2026-09-04-render-store.md`. **Part 1 is
built and its tasks are checked off**: `brick_icons/db.py` holds the schema and
every accessor, `scripts/build-corpus-db.py` rebuilds `corpus.db` from files,
and `tests/test_db.py` covers it.

**Part 2 is built and running.** Every task in the render-store plan is checked
off but the last, which is Mike's to take (below). `brick_icons/batch.py` holds
the guard both batch jobs now share, `scripts/build-render-store.py` renders a
part list into the store, and `scripts/run-render-store.sh` shards it:

    scripts/run-render-store.sh 8 180 naive     # RETRY=1 to re-take timeouts
    scripts/render-store-report.sh              # where it has got to

Parts 3 and 4 — the lab's findings view and the regression gate — are unwritten,
each its own plan.

**The store run needs a second, slower pass.** Resume treats every logged part
as done, so anything the per-part cap cut short is dropped rather than retried.
`RETRY=1 scripts/run-render-store.sh 8 600 naive` takes exactly those, and a
`ProcessDied` part is still never retried. Run it on a quiet box: the first
22 parts timed out at 23% against a desktop running Chrome, and the renders are
single-threaded at ~80% CPU each, so contention is the whole story.

Two decisions taken 2026-09-04, so they are not re-argued from scratch:

**One pass, iso only.** The store holds one canonical render per part per
source, all at iso — the pose the goldens already use. This inherits their
blind spot knowingly: no golden combo sets `--angle`, so nothing here says
anything about other poses, and the one bug that hid was every round part
crashing the naive engine at a side elevation. A second pose costs about 110
CPU-hours per engine — the renders, not the disk, which is ~115MB — so the
version worth proposing later is a side elevation for the parts the database
can already single out, round ones and anything the census flagged, not
another whole pass. Adding a pose needs the pose in the file path, since
`config_key` distinguishes them in the table but the path does not.

**The census's renders stay out of git for now.** They live in
`out/census/renders/<engine>/`, gitignored, with rows in the database. Roughly
16,500 of them at full coverage, ~230MB.

**`db.census_trees()` is the one definition of where those renders are, and a
caller that keeps its own list is a bug.** The census runs one tree per node —
`out/census`, `out/census-naive`, plus run 1's archive `out/census-run1` — so a
caller looking only in `out/census` indexes one engine, returns a smaller number
than it should, and raises nothing. That is the shape that reads as "the census
hasn't finished yet". `rebuild(census_dirs=None)` calls it; pass a list only to
index something narrower.

Each tree is imported as **its own run**, which is the only thing separating
pre-fix rows from post-fix ones: `out/census-run1` is not a disjoint set of
rows but a literal *prefix* of the live files, same filenames continued in
place, and the rows carry no timestamp or commit. Post-fix occt rows are
therefore `run(out/census) EXCEPT run(out/census-run1)` — 2,517 parts, matching
the count `CENSUS-RUN2.md` records as never attempted. **Beware the run ids:**
run 1 in the database is `out/census`, the live tree; the archive is run 3.
Read `args.dir`, never the id.

**The database cannot tell you which code produced a timing, and two traps
follow.** `runs.commit_sha` is whatever was checked out when the *rebuild* ran,
not what produced the rows — it says nothing about the engine that timed them.
And a run is a directory, so job `62bb81bd`'s pre-fix rows sit in `out/census`
beside the backfill's HEAD rows and share a run id. Comparing engines off the
database alone therefore reads occt as 1.16x slower than naive when it is
about 2.5x faster; `scripts/census-plot-engines.py` reads the HEAD timings from
`out/census/backfill/*.jsonl` directly for that reason. Accuracy is unaffected
— the SVG is byte-identical across the perf commits — this is a timings-only
hazard.

A part drawn by two trees under one engine is **one row**, won by whichever
tree sorts last — the nodes run an engine each so nothing collides today, but
an archive carrying renders would, and the render total would not move. The
rebuild counts it as `replaced` rather than leaving it silent. Renders sitting
directly in `renders/` instead of `renders/<engine>/` are skipped: three
`<part>.occt.svg` files from an early smoke run are there, and their stem would
file a row under a part id that does not exist.

**`corpus-grouping` was cut before `census_dir` became `census_dirs`** and its
`_rebuild()` test helper still passes the old name in four places, so its
tests raise `TypeError` rather than conflicting. It matters only if that
branch is ever revived; nothing on main or in v2 carries it.

**The tracked store is bigger than that, not equal to it.** Measured on the
first stored renders, the canonical stroked drawing has a 29KB median and a
long tail — `0901` is 699KB of real geometry, 1481 elements, already at 2dp, so
there is no precision bloat to trim. That puts the naive half between 230MB and
640MB, and the run leaves `renders/` **uncommitted** for that reason: the
rendering is the expensive half and it is safe on disk, so committing later
costs nothing. Firm the number up with `du -sh renders` and decide then.

The decision that shaped it, argued in conversation: **a render is the most
expensive artifact this project makes, so `renders/<source>/<part>.svg` is
tracked in git and the database is derived from it.** Not the other way round.
Store the SVG plain rather than gzipped — git's own zlib and delta compression
are what make a re-rendered part nearly free, and a pre-compressed blob defeats
both. `corpus.db` is gitignored and rebuilt by walking `renders/` and the TOML.


## The corpus wall — merged to `main`

A pan/zoom canvas showing every one of the 24,591 parts as one cell, thumbnail
where a render exists and a status color where none does. Merged as `d54ca18`;
all 23 tasks of `docs/superpowers/plans/2026-09-05-corpus-wall.md` landed.

Run it: `.venv/bin/python -m brick_icons.lab` and `cd lab && npm run dev`, then
`/corpus.html`. `scripts/index-census-renders.py` indexes census renders and
`scripts/bake-thumbs.py` bakes the sheets; both are idempotent.
### 2026-09-06: the wall, after a day of it

Committed on `main` through `a3f5b90`, **unpushed**. All of it is live at
`/corpus.html` with `.venv/bin/python -m brick_icons.lab` and `npm run dev`
running.

**A schema bump means restarting the lab server on 8792, and it is part of
landing one rather than something to notice afterwards.** The server is
long-lived and `scripts/census-ingest.sh 900` rebuilds `corpus.db` from the
working tree every 15 minutes -- so a bump goes live on the next tick,
underneath a server still holding the old schema, whether or not anyone
restarted anything. Every cells request then fails (`no such column: source`
was schema 2's version of it) and the wall draws blank, which reads as a
frontend fault and has cost an hour twice. `db.py` has no `ALTER` path at
all: `SCHEMA_VERSION` goes up and a rebuild recreates the table. Restart
8792, and say in the commit that you did.

**What a cell knows.** `part_years` carries first year, last year and set
count for 9,269 parts, derived from Rebrickable's public dumps by
`scripts/fetch-part-years.py` into the committed
`tests/goldens/part-years.csv` -- `db.rebuild` reloads it, because a rebuild
drops the database and the ingest cron rebuilds every 15 minutes.
`brick_icons/tags.py` turns those plus the library's category and flags into
tags: sticker, minifig, technic, duplo, printed, obsolete, retired, popular,
obscure. Retired means the last set is two years back; obscure covers the
sideline themes whatever their set count; a part the catalogs do not list gets
neither popular nor obscure, because that is missing data rather than rarity.

**What a cell shows.** Its state color, and now: a slash corner to corner when
it is undrawn and bordered; its state's border over the thumbnail when it is
drawn (under the drawing at the vector rung, over it on an opaque bake); a
gray R bottom-right when retired and a goldenrod star top-left when popular;
its years top-right and its part number bottom-left past 110px; and a wash
over the whole cell when retired, painted by the viewer at
`params.retiredWash` rather than baked -- **the bake has one ground again**,
and changing how a retired cell looks costs a repaint, not 7,600 rebakes.
Out-of-scope cells are not squares at all: a lavender sticker glyph, or the
category's initial, at 60% of the cell.

**What is out of scope**, in `db.OUT_OF_SCOPE_CATEGORIES`: `Sticker` and `|`
(LDraw's mark for a part nobody at LEGO made -- Circuit Cubes, Brickstuff,
Hubelino, BuWizz). 2,794 cells. Separately, `~Moved to` redirects are hidden
from the view rather than dropped from `parts`: a cell's sprite position is
its index over the whole corpus, so removing them would renumber every sheet.
Checkboxes in the filter bar bring both classes back.

**A `wontfix` defect has its own state** and its own count. It used to be
counted as open, so a fault someone decided to live with painted exactly like
a live one.

**Chrome.** The lightbox is a modal portaled over the shell header, showing
the part as every slot drew it, with links out to Rebrickable, BrickLink,
Brickset and the LDraw library, an `Open in lab` link (`index.html?part=<id>`)
and a form that files a defect against the slot being viewed. A drag or a
wheel drops the hover card. A slot change keeps the old drawings up until the
new slot's cells and sheets are both in hand. A pan stops a panel width plus
30px past the wall's edge. Numeric params carry units through a resolved
schema, since a legacy `ConfigField` cannot hold one.

**Bugs found and fixed along the way, worth not re-finding:** the vector rung
canceled every raster in flight on each camera frame, so a zoom threw the work
away and started over; the same cancellation was in the loose rung, where a
dropped image was never re-requested; `engine_for` took everything after
`census-`, so both white slots asked for measurements from an engine called
`white-naive` and joined to nothing; and two bakes running at once dropped
5,110 entries from two slots' `baked.json`, which the wall reads as "stale"
and draws as a blank cell (that was the 29111 report). The last one is why
`e60f811` writes sidecars atomically -- and why only one bake should run at a
time.

**The blur after a slot change is fixed** (`f9a3801`) -- the "SVG pop-in, or
possibly even mipmapping" report. A zoom is not what broke it; switching
slots is, and it is only visible if you switch while zoomed in. Two causes,
either enough on its own. `setLevel(32)` on a slot change threw away the rung
the camera asked for, and nothing recomputes the level but a camera move, so
the wall sat on the 32px sheet until the next wheel tick. And
`useVectorThumbs` cleared its raster cache through `setRaster`, which the ref
the work-splitter reads does not see until the next commit -- so the new
slot's cells were matched against the old slot's rasters, which a parked
camera makes look exactly the right size to keep, and they were neither drawn
nor redrawn. The second one *is* a regression from the slot hold (`1117576`):
the blank frame it removed used to give the cache clear a commit of its own.
**The level belongs to the camera, not to a slot** -- every slot lays out the
same 24,591 cells at the same size, so nothing about a slot change should
touch it.

**Still open.** Badges and captions are not toggleable, and Mike wants them
to be. The census draws the `~Moved` redirects, which are hidden on the wall
and can never be worth rendering -- skipping them in the batch lists would
give back whatever share of the run they are. A 512px baked level between the
128px PNG and the SVG was considered and deferred once the vector rung got
fast; it would cost roughly 600MB per slot.

**`~/src/castleblack`** holds the design for pulling the wall out into two
domain-free packages, with this corpus as the first host --
`docs/superpowers/specs/2026-09-07-abstract-wall-design.md`. The earlier
`wall/README.md` it superseded survives only at `a1fffd0`. Its first phase is
built here on branch `states-as-data`: the cell states and the selection
vocabulary are now tables, behind 45 `paintCommands` goldens. Nothing in this
repo imports anything from castleblack, and nothing is meant to until the
packages exist.

**Grouping is on the wall.** `corpus-grouping-v2` merged, giving the sidebar
four groupings -- nothing, coverage, category, release year -- an order and a
color ramp, category and class facets with live counts, and band labels over
the blocks. Design and plan:
`docs/superpowers/specs/2026-09-05-corpus-grouping-design.md` and
`docs/superpowers/plans/2026-09-05-corpus-grouping.md`.

**`corpus-grouping` -- the older, 20-commit branch -- is not merging, and
that is a decision, not a backlog item.** It carries the same grouping core
(`grouped.ts` and `layout.ts` are byte-identical to v2's) on top of a second
Rebrickable pipeline of its own: `brick_icons/rebrickable.py`, a
`part_facts` and a `part_colors` table, `scripts/import-rebrickable.py`, and
a `cells.py` that sends `cat` as an index into a `categories[]` array plus
`year`/`uses`/`ncolors`. Main already answers all of that from `part_years`,
`tests/goldens/part-years.csv` and `tags.py`, offline and without a network
fetch of 1.5M inventory rows -- which matters, because the ingest cron
rebuilds every 15 minutes. Its `useCells` also predates the slot hold and
returns a bare body rather than the `{cells, source}` pair. **The one thing
it has that main does not is a color count per part**, which is why its tint
offers `colors` and v2's offers `year` and `sets`. That is being added to
main's own pipeline instead, as a `colors` column on `part_years`.

**Band labels overlap the top cell row when the whole wall is fit to width.**
`grouped.ts` reserves `headerRows * pitch` of world space above every block,
but `paint.ts` draws the label at a fixed 18px (outer) or 11px (inner), so
below roughly a 20px cell the text is taller than the gap it was given. There
is a width guard (`MIN_LABEL_PX`) and no height one. Zoomed in, labels sit
clean.

**windease cannot lay out this wall, and the caret already has what it offered.**
`gridStrategy.layout` is O(n^2): 6.4ms at 250 items, 18.7s at 16,000, 44.7s at
24,591 — measured, exponent 2.0 across the range. Its `focus/resolve.ts`
`directional()` is the same score function `lab/src/corpus/caret.ts` already
uses (nearest center along the axis, plus a cross-axis penalty), and taking it
from windease would mean a `Store` node per cell. Do not re-propose it for the
corpus wall. It stays the right tool for slopboard, which lays out tens of
panes and not tens of thousands.

## Lab decisions from 2026-09-04, none of them in the code

**The three layout buttons name windease's own strategies.** windease
(`~/src/windease`, its own repo, reaching the lab as a labkit dependency) ships
`grid`, `split`, `stack`, `strip` and `floating`. The lab reimplements three of
them as CSS classes in `lab/src/app.css`, which is how `grid` came to lay four
panes out in a row of four — windease's grid auto-balances. The `:has()` column
counting there now is a stopgap standing in for that; the panes should become a
windease zone.

**A key that temporarily arms a toggle gets its own half-pressed state**, not
the on state — `.pose.is-armed` against `.pose.is-on`. A clicked toggle stays
until clicked again; a key-armed one returns on release, and drawing them alike
makes the button look stuck. Alt on the loupe is the first case; write the next
one the same way.

**Two asks are blocked on the same missing seam.** labkit's `StringNode` offers
`placeholder`, `maxLength` and `debounce` and nothing else, and its node tree
has no read-only text leaf. So committing the part field on Enter, and showing
the selected part's name inside the settings panel, both need the lab's first
custom control (`f.custom` + `controls`). Worth building once. The part field
is throttled with `.debounce(400)` meanwhile, and the trial titlebar already
reads `3001 - Brick 2 x 4`.

**labkit is pinned to the released `@weasel-js/labkit@^1.4.0`.** One labkit
commit landed after that tag — `a2c5318c`, bundling declarations from built
types rather than source — so if a labkit type ever resolves oddly, that is
why and 1.4.1 is the fix.

## Read first: there are two threads now

**Branch state (2026-09-04):** `labkit/annotations-arc-5` is fast-forwarded
into `main` and the whole arc is on it. **`main` is 27 ahead of `origin/main`
and nothing is pushed.** The `BRICK_GOLDENS=full` run that gates the engine
files this arc touched — the colour-to-color rename across `hlr`, `occt`,
`shade`, `trace`, `unwrap` — finished green at 00:59 (751 passed, 4 skipped,
18m04s), before the two lab-only commits on top of it; a lab commit cannot
move a Python suite. Only the tail of that run's log survived, so the
`BRICK_GOLDENS=full` on its command line is inferred from the duration and
from three tests un-skipping, not read.

**labkit is pinned to the released `@weasel-js/labkit@^1.4.0`.** The `file:`
link to the weasel checkout is gone, and with it the requirement to rebuild
that checkout before the lab could see a kit change. `lab/vite.config.weasel-src.mts`
still exists for running against weasel source when a kit change needs to be
seen before release — it is opt-in with `--config`, never the default.

The **corpus lab** — a local web app for inspecting renders and tracking
defects — is the active one. The engine thread below it is unchanged and still
true; skip to it if you are here for `occt`.

### The lab, and what is in it

Design: `docs/superpowers/specs/2026-08-31-corpus-lab-design.md`. All five
plans in `docs/superpowers/plans/` are executed and their walkthroughs run.

Run it: `.venv/bin/python -m brick_icons.lab` and `cd lab && npm run dev`, then
open `http://localhost:5178`. Gates are `.venv/bin/python -m pytest -q` and, in `lab/`,
`npx vitest run && npm run typecheck` (351 frontend tests).

Two instruments. **Part inspector**: a pane per enabled source — `naive`,
`occt`, LDView, an orbitable 3D view, a printed part's decal, and a pixel diff
— sharing one 2D camera, with the pose bar's toggles writing `config.sources`.
**Contact sheet**: a corpus list rendered as one batch job, cells appearing as
they finish, clicking one opens it as a trial.

Also: drag on a pane with `mark` armed to file a defect against what is on
screen (`tests/goldens/defects.toml`, regenerated into this file's Open section
by `scripts/defects-to-handoff.py`); "check goldens" re-renders a part once per
combo and compares each sha256 against `tests/goldens/hashes.txt`.

**The loupe**: hold Alt over a pane for a magnifier that follows the cursor
without moving the shared camera; Alt+wheel sets how much. The pose bar's
`loupe` button makes it stick without the key and `all panes` mirrors it onto
every pane sharing the render fit — the engines and the diff, not LDView or the
decal, which are framed differently. Design:
`docs/superpowers/specs/2026-09-01-loupe-design.md`.

### Traps

- **`.venv/bin/pytest` in a worktree tests the MAIN checkout's library.** The
  venv is shared and its editable `brick_icons` is rooted at the main clone, so
  a console-script `pytest` imports that one -- including whatever is
  uncommitted in it -- and the worktree's own `brick_icons/` never loads. It
  fails loudly only where the branch has a feature main lacks (`test_occt.py`'s
  two full-turn tests); everywhere else it goes green against the wrong code.
  Run `.venv/bin/python -m pytest`, which puts cwd first on `sys.path`, or
  `PYTHONPATH=$PWD .venv/bin/pytest`. A `-m` invocation such as
  `python -m brick_icons.cli` was never affected, which is what hides it.
- **`seen` and `renderSignature` answer different questions — do not merge
  them.** Both ask "is what I am looking at still the run this belongs to", and
  merging them looks obviously right. It is not. `identity.ts`'s `SEEN_KEYS` is
  the three flags a mark's POSITION depends on (`angle`, `shading`,
  `shade_style`), and it excludes `--render-px` on purpose because a fractional
  mark does not move with resolution. `renderSignature` is the part plus every
  flag `renderConfig` passes — about thirty — because any of them makes a
  different drawing. Route `seenMatches` through it and bumping `line_width`
  dims every mark on the pane, none of which moved. "Is this the same drawing"
  and "is this mark's geometry still valid" are two questions.
- **`segments_to_svg`'s short-fragment cull: do not "fix" it by moving it after
  `_chain_line_ops`.** The cull drops a line shorter than 0.6 stroke widths as
  a cap dot, which erased every curve the cadquery engine draws (2463 ops in,
  21 line commands out) because a discretized curve is nothing but such
  fragments. The fix that landed keeps a fragment that is one link of a RUN of
  three or more joined end to end. Moving the cull after chaining is the
  obvious alternative and is wrong: measured, it closes two pinch notches on
  `32062` but reintroduces a 46px wart on a `6589` stroke — the exact thing the
  cull exists to remove — and drifts 18 of the 52 golden cases. A wart chains
  happily to the long strokes either side of it, so chaining cannot separate
  noise from curve; the run can. Landed in `466c8ac` by the cadquery session,
  not re-derived here.
- **The API server does not reload.** `python -m brick_icons.lab` serves the
  routes it started with, so a route added mid-session 404s until you restart
  it — which reads exactly like the frontend being wrong. Three separate
  bugs this session were this. Vite hot-reloads; the Python side does not.
- **labkit's design tokens are `--wzl-*`; only its DOM classes are `lk-*`.**
  Every `var(--lk-border, …)` in this repo silently took its fallback, so
  panels rendered dark-on-dark in the light theme. A `var()` fallback makes
  this fail silently by construction — there is no error to see. Fixed
  throughout; weasel now documents the split in labkit's `RECIPES.md`.
- **A `role="button"` span inside a `FloatingPanel` is dead to a real mouse.**
  The panel captures the pointer on pointerdown and exempts only
  `input, button, a, select, textarea, [data-no-drag]` by element NAME, so a
  span is captured, mouseup retargets to the panel, and no `click` is
  synthesized. A programmatic `.click()` still works, which is how it hides.
  `App.tsx` stops the drag on the panel body; delete that when labkit's
  movement-threshold fix ships. The same shape bit the mark layer over
  `.pane-body`, which captures to pan — `MarkLayer` stops it there too.
- **`jsdom` synthesizes a click whether or not the pointer was captured**, so a
  test asserting "the handler fired" passes against both the broken and the
  fixed code. Neither bug above is unit-testable that way; both were found by
  driving a real browser.
- **`--list` names a FILE of part ids.** The contact sheet's `list` config is
  the lab's own field and must stay in `LAB_ONLY`; leaking it renders every
  part with `--list manifest:spread` and fails the whole sheet.
- **Port 8792.** 8765 is taken by brainhouse and 8791 by an unrelated
  `http.server`; the default moved twice. `lab/vite.config.ts` proxies to
  whatever `brick_icons/lab/__main__.py` defaults to — change both together.
- **Never `sed -i` a file with non-ASCII in it.** macOS sed corrupts multibyte
  characters; it silently mangled a plan mid-session. Use Python or Edit.
- **`cli._config_from_args` still maps args to overrides by hand.** A new CLI
  flag needs a line there as well as its `add_argument`, and
  `tests/test_lab_schema.py` will not catch the omission — it derives from the
  parser, not from the override dict.
- **Two CSS rules reach into labkit internals**, both commented with what
  deletes them: `.lk-trial__title` is hidden so the part title can lead, and
  `.lk-trial__titlebar-actions` is stretched so a contribution can sit at its
  left. labkit has now moved Clone and Reset into that same span, so the
  ordering is worse until the leading-slot fix ships.
- **`LDrawLoader` searches `parts/`, `p/`, `models/` before trying a name as
  is**, so its 404s in the console are its normal search and not a failure. It
  also needs `setConditionalLineMaterial` since three 0.170, and rewrites an
  `s/…` reference to `parts/s/…` itself.

### Traps the cleanup pass left behind

The lab's cleanup list is finished. What is worth carrying forward is not
what was done but the three places where the obvious reading is wrong:

- **`caveat` is gone from the `Source` type** — a pane carries a bare label
  and an optional `note`, which is a measurement it made, not a standing
  remark about the source. Do not reintroduce it.
- **A `%2F` in a path never reaches a route handler.** Starlette leaves it
  encoded, so `/api/artifact/{key}/{name}` does not match and the caller gets
  a 404 from the router. A traversal test written against that URL passes
  whether or not the guard exists — `_artifact_path` is tested directly for
  that reason.
- **`[data-no-drag]` says "do not drag me", which is not the same as "this
  press is mine".** Marking `MarkLayer`'s marks stopped the pane panning under
  them, but a press on one still reached the armed layer beneath and started a
  fresh mark. A layer that both draws and holds targets has to start its draw
  on itself, not on whatever was pressed.

### What the walkthroughs actually established

Not re-derivable from a green suite, and each cost real time:

- `3001`'s studs point up in the 3D pane, and `top`/`left` agree across all
  four panes — the LDraw Y-flip and the longitude sign are both right.
- Orbiting fires exactly one LDView render per settle, not one per pointer move.
- The lab's `outline-flat3__3941` digest is `d53feb17…`, byte-identical to an
  independent `shasum` of a fresh CLI render and to `hashes.txt`. The lab's
  golden answer means what pytest's means.

### Upstream

Linked, not pinned — see the link paragraph above for how to advance it.
labkit ships `AnnotationsApi.selection()` and `setSelection()`, and the styling
contract is in its `docs/RECIPES.md`. The `FloatingPanel` capture is filed
upstream, not fixed, so `App.tsx`'s drag-stop stays. The `.pair()`-vs-`pack`
question and the leading titlebar slot are filed and open.

`usePanZoom` is exported standalone, for a lab that hosts its own renderer
through `surface` — which is what `lab/src/panes/camera.ts` is. Nobody has
checked whether its view shape matches what an annotation target wants.

The icon set is reachable as `import { Icon } from '@weasel-js/labkit/weasel-ui'`
— the bare barrel does not carry it. The pose bar's layout selector draws from
it. `weasel-ui` is the passthrough for every kit primitive, so importing
`@weasel-js/ui` directly is never the answer.

Sidebar sections can now be torn out into workspace tiles (`undockAs`), but a
section undocks WHOLE, as one panel: our six settings sections would become six
tear-out controls and six panels. Putting the render and color flags in one
tile means making them one `sidebar` contribution with both groups inside it,
not two contributions — so this is a restructure of the panel, not an
annotation on it.

**Sidebar drag-to-resize is in the linked tip** (`21b0582a`): the sidebar and
content well are a two-pane windease strip whose seam is a real
`role="separator"` — pointer drag, arrows, Home/End — with the width persisted
per trial as `TrialRecord.sidebarWidth`. Nothing here needed changing for it:
we use neither `--lk-trial-sidebar-w` (which stops meaning anything) nor
`<TrialBody>` (for chrome you compose yourself). Nobody has driven it here yet.

Do not wait on any of it; every item has a working local workaround.

### The annotations overlay owns pane input

`paneSpec().marks` now answers "does this pane take marks *right now*", and
`config.marking` is half of it, so a target — and the `.lk-annotate__input` box
that covers a pane and takes every pointer event it would otherwise pan with —
mounts only while marking is armed. **Filed defect marks are therefore hidden
while it is off**, which is what the toggle promises; the Defects panel still
lists them. The trial also starts on `rect`: an instrument declaring only
`annotations` opens on `select`, where a drag marquees rather than draws.

**Still open: whether the camera should stay live *under* an armed overlay.**
`usePanZoom` above is the likely answer. Nothing here is visible to jsdom —
all three were found driving a browser.

A projected mark could not go stale, because the projection passed the live
config to `marks.add` and re-ran on every config change. `buildDefect` fills
`seen` from `POSITION_DEPENDS_ON` again — the TOML store never stopped keeping
the field — and `projectDefects` dates each mark by that. A record filed
between `f1638fc` and `d6d9293` carries `seen = {}` and never goes stale, which
is what labkit's `isStale` does with an absent key by design.

## The engine thread: one checkout, no branches

`occt-port` is merged and both its branch and its worktree are deleted, so
this is a single-checkout repo again and the two-workstream protocol below is
history — kept because the lesson still applies if the repo is ever split
again. The port's task briefs, reports and review diffs survive under
`.superpowers/sdd/` (gitignored), moved out of the worktree before removal.

Landed: `50950`'s elliptical wall, arcs read off the projected conic rather
than HLR's BSpline approximation, and a silhouette contour for the OCCT
engine. The defect list below is rewritten against the merged corpus.

## Corpus review 2026-08-31 — the acute-angle family, diagnosed and fixed

One cause explained the boreholes, every gear centre, and the axle's notch
pockets: **`arcfit.fit_edge_arcs` MOVES a fitted chain out of `out["2"]`, and
`occt.authored_loci` built its loci from `out["2"]` alone.** Every chain arcfit
claimed was therefore structurally undrawable in `occt` — silently, because a
locus that matches nothing is not an error. It is the chains at acute junctions
that arcfit claims, which is why the symptom picked out axle holes, gear hubs
and notch pockets and left plain boxes alone. `3941` lost 40 of its 120 type-2
edges that way; `3649` lost 200.

Three fixes, all in `occt.py`:

- fitted chains reach `authored_loci` through `out["fit_arcs"]`, matched as the
  authored chords (the shape's own fragments ARE those chords and miss the arc
  by the sagitta);
- a matched chord fragment is re-read against the fitted circle, so `occt`
  stylizes the chain the way `naive` does instead of drawing two chords meeting
  at a point;
- collinear seg loci merge before matching. `ShapeUpgrade_UnifySameDomain`
  welds collinear edges across subparts, so one fragment can span several
  authored segments and lie inside none of them — `32062` authors its axial
  ridge in five pieces (three `axlehol8` sections plus the two notch spans) and
  gets back one edge running the whole axle.

**`3941`'s naive borehole was never wrong.** The disputed "red herring" call was
right, for a reason nobody had written down: what it draws IS the authored
axle-hole rim — verified edge by edge against the projected type-2 lines, and
against LDView at matched elevation. The near lip is hidden because the front
stud stands 4 LDU proud and, at 30 degrees, its shadow reaches past the lip
(clearing it needs 6.93 LDU of horizontal run against the 4.60 available). Only
`occt` was drawing it wrong, and it drew nothing at all. Re-deriving this costs
an hour; do not re-open it on the strength of the render looking odd.

Two `arcfit` changes, both on the NAIVE path, both re-frozen into the goldens
(12 of 52 cases moved; `A` rises and `L` falls in every one):

- **A neighbouring chord is not a tangent.** It lies half its own sweep off its
  circle's tangent, so on 16-gon tessellation (11.25 degrees against
  `ANCHOR_ANG`'s 15) it reads as a continuation of whatever chain it touches.
  On `3941`'s stud truncation that anchored the fit onto r=4.7 where the chain's
  own vertices sit at 6.8, the residual gate then rejected the chain, and the
  whole truncated quarter drew as a kinked polyline beside the smooth
  270-degree arc. `_fit_circle` now falls back to the unanchored fit when the
  anchored one fails its own residual — and reports zero anchors, so the
  lopsided-chain gate below still applies.
- **`SYM_RATIO` 1.25 -> 3.0.** A real round authored on a slanted plane
  projects to an ELLIPSE, so its sweeps are unequal however evenly it was
  faceted — `54200`'s inner corner is 1.57:1 and drew a 38-degree kink beside
  its own smooth outer ridge. Sited by measurement over the specimen list: real
  rounds run to 2.66, and the first fabricated fit is `32062`'s axle end at
  4.16, which balloons each end into a blob reaching r=6.59 on a part whose
  profile radius is 6.0. Both sides are pinned by tests.

### Still open from that review

- **`4019`'s hub rim.** naive draws a 278.8-degree sweep on a conic of
  semi-axes 13.79 x 10.67; `occt` has that locus, matches one of the eight, and
  draws a different conic (14.88 x 9.11) instead. **Not** `UnifySameDomain` —
  building the shape without it changes neither the sharp-fragment count (481)
  nor the match (1 of 8). Undiagnosed.
- **`4070` (occt): the base ledge's top edge is TRUNCATED, not gone** — it
  draws as two short stubs, one at each end, with the whole middle missing.
  `4070` has ZERO arcfit-claimed edges, so it is not the family above. Still
  the cleanest reproduction of a dropped edge on a simple, fast part. It used
  to read as a ragged dotted line because the fill seam underneath was a
  1.2px staircase; that seam is straight now, so what is left is purely the
  missing stroke. See the memory note for three disproofs and the one
  segment that measures as naive-only.
- **`4070` (occt): a dark unstroked wedge past the SNOT stud's outer rim**,
  at roughly 1:30 on the stud, lying on the front wall where naive draws
  plain wall. It is fill op 7 of 11 — a GRADIENT (so a curved wall span,
  not a plane), depth -0.59, bounded by 4 arcs and 0 lines. So a stud
  cylinder's span polygon is painting outside the stud's own silhouette,
  the class `_refine_order_clips` calls "a wall span polygon overhangs its
  own silhouette". Both spans measure span_deg 180, so it is NOT the
  full-turn/end-on-cylinder case. Undiagnosed; predates the fill work
  (0 pixels move across it).
- **`32062` (occt): both bottom notches carry two stray fill elements
  each**, and they are the SAME defect twice — the pairs sit at
  (66.3, 92.2)/(156.5, 137.3) and (67.3, 93.8)/(157.5, 138.9) in a 700px
  render, an offset of exactly (90.2, 45.1), which is the notch spacing.
  Each notch gets a 9.8 px^2 three-vertex `#5e5e5e` triangle with a 0.6 px^2
  black one inside it. Rank the emitted fills by area to find them again;
  they are the four smallest of 26 subpaths. Undiagnosed — spotted on the
  face sheet, never chased. Something is also off on the BACK EDGE of the
  frontmost bottom notch (naive-vs-occt diff component, 2028 px centred
  (438, 352)); not characterized at all.
- **`3673` (naive): only the front notch has its rounded end pocket.** Also
  zero arcfit-claimed edges. The earlier guess that this and `32062` were one
  bug is dead — `32062`'s was the locus gap, and `3673` has no chains at all.
- **`99781`: a vertical line right of the hollow SNOT studs is missing.**
- **`6589`'s misaligned halo on the naive path — diagnosed, unfixed.** It is
  the counterbore separator refit, and it does sit under the 10x cap: two
  refits, the authored r=16 ring onto r=12.80 (sweep 121.72 -> 220.79, 1.81x)
  and the authored r=12 onto r=11.33 (180.00 -> 344.69, 1.92x). `6589.dat`
  authors circles only at r=9, 10, 12 and 16, so both are fabricated.
  `SEP_REFIT_MAX_GROWTH` bounds the ANGULAR span only; the refit is free to
  land on a circumcircle of any radius, which is what needs a guard. `occt`
  draws the authored set and is right here.

## Read this before calling the port nearly done

**`occt` has fills now.** `occt.visible_segments` returns one face per planar
face of the sewn shape and one per limb-cut span of each cylinder, cone and
elliptical wall, ordered by `shade.order_faces` against each curved face's own
exact surface. `--engine occt --shade-style flat3` fills all 21 parts of the
`unprinted` corpus with 0 render failures:

    .venv/bin/python scripts/compare-engines.py --combo outline-flat3 \
      --parts unprinted --sheet /tmp/sheet.png

`OCCT-MIGRATION.md` is still the roadmap. Items 1 and 2 are done; 3, 4 and 5
are not, and `occt` is still not the default.

**Look at faces, not at drawings — `scripts/render-face-sheet.py`.** One flat
color per fill element, strokes dropped, over any part list:

    .venv/bin/python scripts/render-face-sheet.py --engine occt \
      --list specimens.txt

The ordinary sheet paints a 2px stroke over every seam, which is exactly
where a fill defect hides. `4070`'s ledge seam was a 1.2px staircase for the
life of the port and only ever showed because the stroke that covers it is
truncated. One pass over the 22 specimens turned up, unchased: `3941`
arrow-shaped artifacts on the top face, `6143` slivers, `3673` stripes,
`3040bp08` fragments, plus the `32062` notch elements listed below. None of
those are in the defects file yet. Note `--debug-colors` is NOT this — it
recolors strokes and leaves the fills grey.

### Where it still differs

Structure agrees across the corpus and the fills shade like naive's: faceted
curves union across their declared type-5 seams and share one gradient, and
face-boundary conics are arc-recovery candidates. `A` rises on the round parts
— which is what `OCCT-MIGRATION.md` predicts — and `L` lands at or below
naive's on 18 of 21 (`3649` 21889 -> 16000, `4019` 3733 -> 2421, `3942c`
1428 -> 402, `4740` 350 -> 16, `99781` 152 -> 75) — all measured BEFORE the
buffer fix below, which moved both engines, so re-measure before quoting.

**The three parts that drew far more line commands than naive were
inheriting a shapely `buffer()` boundary.** It was neither the HLR nor the
fills' own sampling: on strokes-only `outline` all three already agreed
(6 -> 12, 49 -> 49, 97 -> 95), and their fill faces reached `fill_ops` with
FEWER vertices than naive's (`4589` 854 against 1320). `fill_ops` added the
rest, in the two stages that hand a region between elements on a coverage or
order decision. Both bound that region with a `buffer()` whose round joins
tessellate at ~0.05 px, and the fragments cut against them keep every vertex
— on a boundary sitting half a stroke off the true arc, where no arc
candidate can absorb it. 1020 of `32062`'s 1290 fill segments were shorter
than a quarter pixel, in runs up to 104 long.

`_stroke_band` is FIXED: it simplifies itself now (`DECISION_SIMPLIFY`), and
cleaning the band rather than the pieces cut from it is load-bearing —
simplifying the donated piece instead moves the donation fixpoint and swaps a
31px tone sliver on `32062`'s axle end. `4589` 498 -> 88 and `32062`
1377 -> 424, gated by
`test_a_fill_boundary_carries_no_stroke_band_tessellation`. Naive fell too
(90 -> 73, 435 -> 377) since the band serves both engines.

**The render goldens are re-frozen for it, and the whole drift is measured.**
All 29 strokes-only `outline` and `wireframe` cases are byte-identical — the
band and the refine pass only bound fills. All 23 `outline-flat3` cases shed
vertices: `3649` `L` 21889 -> 12630, `4740p03` 5621 -> 5055, `4019`
3733 -> 3333, `3941` 1417 -> 1186, `3673` 1015 -> 654, `6143` 1059 -> 859,
`32062` 435 -> 393, `4589` 90 -> 53.

Almost nothing moves on screen, but "zero pixels" is no longer true now that
the refine rewrite is in the measurement. Counting pixels off by more than 8
grey levels: `32062` and `3941` 0, `3649` 5, `4019` 84 — one sliver in a gear
recess, the trade the rewrite's own note predicted — and the printed parts
carry decoration hairlines that shift, `3040bp08` 2, `3941p01` 41, `4740p03`
367 in 53 components, none bigger than 155 px. Peak grey deltas reach 135
(`4740p03`) and 106 (`3941p01`) on those hairlines. Rendered before/after
pairs were compared for all of these; nothing structural moved.

**`_refine_order_clips` sampled a straight answer.** Two planes' depths are
both affine in screen space, so "is `idx` in front of `j`" is one affine
inequality and the region it wins is an exact half-plane. The pass
grid-sampled it at 1.2 px anyway, which quantized `4070`'s ledge seam into a
staircase and spent 315 vertices per face on it — visible because the stroke
that should cover that seam is truncated to two stubs (a separate HLR bug,
see the memory note). It solves the all-planar case in closed form now and
runs the lattice only on the part of the region a CURVED coverer overlaps,
since only a curved surface can also MISS the ray. `4070` 719 -> 100 against
naive's 104, the ledge face 315 vertices -> 10, and `3673` — the part the
pass exists for — is pixel-identical.

Two traps in that closed form, both of which produce a plausible wrong
picture rather than an error. A coverer occludes only INSIDE ITS OWN
POLYGON, so the take is `region - (geoms[j] AND half-plane)`; clipping by the
unbounded half-plane instead let a face erase area it does not cover, and
4070's ledge top vanished. And the all-planar test has to be per-coverer:
gating on "every coverer is a plane" fell back to the grid for the whole
region because the ledge's lost area also grazed the stud walls.

Parts whose refine regions genuinely involve a curved coverer still run the
lattice and still carry its tessellation (`3941` 51 sub-quarter-pixel
segments in a row, `4019` 64). Simplifying THAT is a real trade — it moves
pixels (a `4019` gear-recess sliver, a NEW `4740p03` hairline) — and nobody
has called it. Gating on the unsimplified area does not avoid it; tried.

What separates the two engines after all that is the span boundary: 42 of the
200 edges on `4589`'s cone-wall ring lie on no arc candidate and emit as
chords where naive's counterpart emits 10. `geom2d._assign_edges` is where to
look; undiagnosed.

### occt-only defects

- **`4070`'s see-through right wall: FIXED**, and the cause was the back-face
  cull. Sewing does not orient faces consistently — 4070's near right wall
  comes back oriented away from the camera and its far twin toward it — so
  culling by orientation dropped a visible wall and the brick's hollow
  interior drew through the hole. There is no plane cull now; `order_faces`
  covers a hidden face by painting it early, and the tone normal is flipped
  toward the camera the way `primitives._flat_face` does. Do not reinstate a
  cull keyed on orientation, and do not orient the shell first: that assumes
  a closed solid, which LDraw parts are not.
- **bbox shifts**: `3941` 1.18, `6589` 5.11. Every other part is under 1.0.
- **`3649` costs 408s** for the naive+occt pair the comparison renders (the
  script does not split them). `order_faces` is O(faces^2) in witness tests
  and 3649 sews 846 faces; ordering 3960's 828 faces alone measured 5.3s, so
  the sort is not the whole of it. Not a blocker; it sets the corpus's pace.

Durable records, none of which this file repeats:

- `OCCT-MIGRATION.md` — what has to exist before `--engine occt` can be the
  default, and what is out of scope.
- `docs/superpowers/specs/2026-08-29-occt-adoption-design.md` — where the OCCT
  engine attaches and what gates it.
- `docs/superpowers/plans/2026-08-28-decal-unwrap.md` — decal extraction.
- `docs/superpowers/specs/2026-08-29-pathops-evaluation.md` — the 2D boolean
  question, settled.
- README, **Golden conformance corpus** — how to run the gates and what each
  artifact is for.
- `docs/occt-port-handoff.md` — the OCCT engine's own open defects, and which
  causes are already ruled out for each. It lived at `HANDOFF.md` on
  `occt-port`, which is this file's path on `main`: one path, two different
  documents, so every merge either conflicted or clobbered one of them. It
  keeps its own path now.

## If you ever split this repo across two sessions again

It cost real work twice, both times the same way: a tree that another session
has checked out will move under you mid-task. Uncommitted `occt.py` was
destroyed by a merge, and three separate measurements had to be thrown away
because HEAD changed between the render and the reading. Check `git log -1`
before trusting a tree you did not just commit to, and commit early in one you
share.

**Merge toward the shared branch, never into the other session's checkout.**
Merging `main` INTO the feature branch first turns the final step into a
fast-forward — a pointer move that touches no working tree, so the other
session's uncommitted files survive. That is how this one landed.

**There is no message channel between two sessions here, and the reason is
structural:** peer registries are per-config-dir, so a `~/.claude-pw` session
and a `~/.claude-msb` one never appear in each other's `ListAgents`. The
protocol is a commit to the handoff the other side reads — which works, but
only at commit latency. Give the two documents different paths up front; one
path holding two handoffs conflicted on every single merge.

## The OCCT engine, as merged

`--engine occt` runs OpenCASCADE's exact BRep kernel for hidden-line removal.
`naive` stays the default and its output is byte-unchanged. `brick_icons/occt.py`
is the only module importing OCP; it is an optional extra and raises rather
than falling back, so a part it cannot draw fails loudly instead of being
reported as a pass.

Faces reach `HLRBRep_Algo` as occluders only. The drawn candidates are the
edges LDraw states, which is what keeps a faceted part from exploding: an
unauthored tessellation boundary is never a candidate, rather than a candidate
filtered out.

Both defects this section used to list were the locus gap above, not what they
looked like. `32062` "losing every arc" was never a missing primitive — its
arcs are arcfit chains, and `occt` had no locus for them. `3941`/`6143`
"rendering their truncated studs whole" was the arcfit anchor bug: the
truncation chain was rejected, so the cut drew as chords. Both fixed; see the
corpus review above.

`50950` is fixed: its wall is a true ellipse, which `frame()` rejected as
shear, so no face was built and the slope had no occluder at all. It now draws
3 arcs against naive's 3 and matches naive's shape, closing the unprinted
corpus at 17 of 17.

**`4589` and `3942c` no longer reproduce the cone-base-ring loss** — the ring
is present in both engines and `4589` draws MORE arcs than naive (23 -> 27),
which is not the signature of losing one. Neither was measured the way `50950`
was, so treat this as a symptom that stopped rather than a cause that was
found; `3942c` sitting 4 arcs BELOW naive (32 -> 28) is the loose end.

The rest match naive's shape, and several are markedly cleaner — `3649`,
`4019`, `6589`, `3673` and `32062` each draw less ink for the same drawing.

**`L` counts now run above naive's on curved parts** (`99781` 109 against 29,
`3942c` 56 against 27). That is the silhouette contour, which the OCCT engine
gained this round and which re-fits arcs only where a DRAWN arc exists to snap
to; a curved surface's profile has none. It is SVG size, not ink — the contour
carries outline the per-edge strokes never had, cutting ink naive has and occt
misses from 537 to 378 on `99781` and 335 to 119 on `6143`. It should
evaporate when fills supplies real faces. Do not chase it with a coarser mesh:
the deflection is a quarter pixel because coarser chords poke out from behind
an exact arc stroke.

Evidence for the open two lives in `docs/occt-port-handoff.md`, which also
records, for the stud, which causes are already ruled out.

**The gate is unprinted parts only**, because a print is authored as ordinary
geometry and a strokes-only combo cannot tell it from the part; printed parts
gate `outline-flat3` instead. `tests/goldens/manifest.toml` has the reasoning
and the substitutions.

**Review renders at 0.65 stroke opacity**, not full — `scripts/compare-engines.py
--sheet OUT.png` emits the naive|occt pairs that way. Single strokes read gray
against doubled ink's black, which is how naive's 30–55% duplicate ink becomes
visible at all.

**`--debug-colors` gives every drawn element its own color** in emission
order. Bare, it is a 12-hue cycle (`trace.DEBUG_PALETTE`) — use it to ask which
element owns a vertex, which a black outline cannot say. `ramp` instead fades
light to dark across 6 elements then steps the hue, so position within a run
and which run both read at once; `ramp=N` sets the run length, and `ramp=100`
trades adjacent-step contrast for coarse structure. It already shows the outer
silhouette is not one contour but many fragments, with the color changing at
each tangent jog. Opt-in; the goldens do not pass it.

**`--part-label` stamps the whole render tag**, not just the part id:
`3941  naive  30,45  outline` (`cli.render_tag` — part, engine, angle,
shading/style, `opacity=` below 1). Engine and angle print even at their
defaults, because a sheet is read after its command has scrolled away. Pass it
on every render meant for human eyes; it is opt-in and the goldens do not pass
it, so it cannot move the byte-diff gate. `compare-engines.py --sheet` needs it
not — montage already labels tiles `{part}-{engine}`.

**Do not trust any per-part table you find written down, including that one.**
Every recorded table in this repo has gone stale within a day of being
measured — the design doc's, the task-7 report's, and three of mine.
`scripts/compare-engines.py` re-derives it in ~10 minutes and is the only
number worth quoting.

## The decision the merge creates

The stray-geometry defects under **Open** live in
`hlr._visible_segments_analytic`. The standing instruction was not to fix them
because the port would replace that code — but the port has landed *behind a
flag*, so the naive path is still what ships, and it still draws them.

Fix them on the naive path. `occt` has fills now, but it flat-tones every
facet group naive gradients (see above), so it is not a drop-in for anything
filled and cannot take the default on that basis alone.

## What shipped

**`brick-icons decal PARTS...`** — extracts printed decoration as a flat SVG
laid out on the face it came from. Dispatched on `argv[0]` alone, so every
existing invocation parses unchanged (pinned by a test). Documented in the
README under "Decal extraction"; flags are `--out`, `--list`, `--root`,
`--config`, `--texture-px`, `--svg-bg` (transparent by default).

Extraction was emitting **nothing** for every part checked before this. Four
causes, all now fixed and tested:

- Carriers were analytic primitives only, so flat prints bound to nothing.
  Body planes now join them (`planes_from`).
- Discs and rings were used as *curved* carriers. `to_uv` sends every
  non-`Plane` carrier through the cylindrical map, where a flat surface has one
  constant height — a round tile's print unwrapped to a zero-area line.
- A round tile's top face **is** a disc primitive, so it has no facets and
  contributed no plane. Flat primitives now contribute theirs.
- Decoration authored as colored *primitives* was ignored entirely.
  `3942bp01` is 16 cone sectors and zero colored facets.

Also: stacked wall sections merge into one spanning carrier (`span_carrier`),
carrier faces union **all** coplanar facets including the print, groups sort by
print area so `.0` is the real print, and `hlr.part_geometry()` skips the view
pipeline (99s → 0.04s on a high-poly torso, byte-identical output, pinned).

**Corpus: 600 parts, 11,855 SVGs, 0 errors.**

## Two deliberate behaviours

**The minifig neck mark is dropped from decals only.** LDraw authors a neck as
a 270-degree body cylinder plus a 90-degree one in black; the head covers it.
It is authored exactly as real print is — `3942bp01`'s stripes partition their
wall into colored and color-16 sectors summing to 360 the same way — so it is
caught by position *and* size together: protrudes past the body **and** covers
no more than a quarter of its ring. Either condition alone admits `29030p01`'s
head print and `53983p01`'s turbine case. Renders keep the band, by request.
`scripts/sweep-marker-prims.py` re-derives this over the corpus.

**Circle recovery is per-run, not per-ring.** `fit_circle` asks "is this whole
ring one circle", which a decal boundary usually is not — a union leaves the
coarser polygon's chord midpoints 0.345 LDU inside the rim. `circle_candidates`
clusters vertex radii, **refits each cluster and verifies it**, then `path_d`
converts only the runs that follow one.

## Open

Filed from the lab; regenerate with `python scripts/defects-to-handoff.py`.
A hand edit between the markers is overwritten — edit the store instead.

<!-- defects:begin -->

### Open

- **`6589`** (naive) at `iso` — spurious ring at r=11.33 (separator refit)
  naive draws a ring at r=11.33 LDU, unauthored the same way as 6589-naive-halo-r12.8. Refit of the authored r=12 ring: 0.944x radius, sweep 180.00 -> 344.69 deg (1.92x, under the same cap).
- **`6589`** (naive) at `iso` — spurious ring at r=12.80 (separator refit)
  naive draws a ring at r=12.80 LDU; 6589.dat authors circles only at r=9, 10, 12 and 16. The counterbore separator refit in hlr._snap_rim_crossings refits the authored r=16 ring onto this circumcircle (0.800x radius, sweep 121.72 -> 220.79 deg). SEP_REFIT_MAX_GROWTH caps angular growth at 10x, so 1.81x passes; nothing guards the radius. occt draws the authored set and is right.
- **`6589`** (occt) at `iso` — this is weird
  Unexamined; y re-anchored from the pane-box fractions the lab stored.

<!-- defects:end -->

- **A round part at any side elevation crashed the naive engine: FIXED** in
  `b5b1ce2`, which guards the snap-tolerance inversion for edge-on rims.
  `3941`, `4589` and `3960` all render at `front`, `back`, `left` and `right`.
  All four pose-bar elevations work on a round part now.

- **`14769p0a`'s `XI` and `XII` render thinner than `IIII` and `III`.**
  Confirmed present at baseline, cause NOT diagnosed. User's hypothesis: they
  sit farther from the camera. Note they read thinner rather than lighter,
  which foreshortening alone does not explain on a flat top face.
- **`14769px2` throws a stray arc outside its silhouette.** Pre-existing —
  verified identical before and after this work. Unrelated to circle recovery.
- **`4019`'s stray ellipse: FIXED, and it was not what this file said.** It
  was never an analytic rim candidate — it was `_snap_rim_crossings`'
  counterbore separator refit re-emitting a 7.2-degree arc as its 310.8-degree
  complement. `hlr.SEP_REFIT_MAX_GROWTH` bounds the growth; `KNOWN_STRAY` is
  now empty. **`14769px2` above is therefore not "the same class"** — nothing
  has been shown to connect them, so treat it as undiagnosed.
- **Sliver policy: settled.** `unwrap.significant_groups` now carries three
  part-level rules — the sliver ratio, the shatter share, and `MAX_DECALS = 4`,
  which returns nothing when a part still resolves to more than a few textures.
  Sited by eye over the corpus, not by the count alone: above the cap a part is
  always ONE decoration cut across faces, never several prints. `20460p09`'s
  five are panels of the same striped garment; `6580ac01`'s six are one band
  cut four ways. The cap counts SURVIVORS, not raw groups — counting raw would
  silence 52 parts whose single print is intact.
- **The extraction seam has a gate now.** `test_frozen_decal_hashes_still_reproduce`
  diffs `decal-hashes.txt` the way the render seam is diffed; a companion test
  fails if a corpus part has no frozen row. `BRICK_GOLDENS=1` re-extracts one
  part per decal-COUNT class (~8s), `=full` the whole 393-part corpus (~6 min).
  Sampling by count class, not alphabetically, is load-bearing: 310 parts yield
  one decal and 20 yield none, so an alphabetical sample misses both edges —
  which is where `MAX_DECALS` does its silencing.
- **`3941`'s notch "rim veer": NOT A DEFECT, and this file said otherwise.**
  The V at the tangent notch is the true projection of the skirt panel's
  bottom corner, the vertex `(11.36, 24, 16)` authored in `s/3941s01.dat`,
  which lands at exactly `(197.56, 134.36)`. Naive's silhouette contains the
  part's own polygons with ZERO missing pixels at `30,65`
  (`scripts/compare-silhouette-truth.py`). The `(198.0, 136.3)` recorded here
  was read out of the `sclip` clipPath, not the outline: it is
  `buffer_d(sil, 1.0)`'s mitre apex at that 60.1-degree corner, matching to
  both decimals. The "barb" is the same corner mitred — ink reaches 1.9px out
  against 1.0px along the rest of the outline, which is what miterlimit 5 on
  `contour_d` is FOR. occt does not emit the point at all today.
- **occt fills that notch in solid, and naive does not.** Same pose, same
  part: occt's silhouette runs 10.1px (99th pct) beyond the part where the
  skirt is cut flat, so the flat walls never reach the silhouette; naive
  holds 0.56px, which is antialias plus arc-over-chord bulge. `4589` also
  loses 686px in 2 components under occt and none under naive. One more
  reason the flag cannot flip — see "The decision the merge creates".
- **`3941`/`6143`'s `stud10` lateral cut: FIXED** — see the arcfit anchor
  fallback in the corpus review. The cut is a cylinder-cylinder intersection
  LDraw approximates with 4 tris and 4 quads; the chain now fits one arc
  through its authored vertices (r=6.8) rather than drawing the chords.
- `SNAP_TOL = 0.4` LDU is the loosest constant added, tuned to the 0.345 stray.
  Extraction only; the render path passes no snap tolerance.
- **`skia-pathops` for the 2D booleans: settled — adopt, but inside the OCCT
  port, not before it.** Conics survive its booleans exactly (8 conics out of
  a two-circle union, 4e-7 area error), so it does delete `geom2d`'s arc
  recovery — but only once true circles reach it, and today every polygon is
  pre-flattened by facet tessellation. It also does not replace shapely: no
  polygon offset, which `opened()`, `close_slivers()` and `buffer_d()` need.
  Robustness is not a differentiator. Measurements and the four binding traps:
  `docs/superpowers/specs/2026-08-29-pathops-evaluation.md`.

- **`naive` shades `4740`'s dish wrong, so it is not the oracle for that
  part.** LDView renders the dish top as a light ramp falling 175 to 143;
  `naive` paints it flat at 86, spread 1. `occt` disagreeing with `naive`
  there was the correct answer, and a parity score against `naive` marks it
  down for being right. Check a shading disagreement against
  `scripts/render-references.py` before assuming the port drifted; that script
  renders "ours" with the DEFAULT engine, so pass `--engine occt` or the sheet
  compares LDView against `naive` and tells you nothing about the port.

## Traps

- **A dome's highlight comes from the light, not from a fit.** Two ways of
  placing it were measured against LDView on `4740` and are worse: the
  brightest SAMPLE's own position puts it at radius 0.37 against a true 1.18,
  and the sphere radius `hypot(Lx, Ly)` at 0.60. A dish's normals tilt only
  slightly from its axis, so the one nearest the light is at its outer edge —
  the rim, 0.95, lands at 1.14. The least-squares slope `_radial_focal_stops`
  fits for the faceted path sat 71 degrees off the light on the same part.
- **The cluster refit is load-bearing.** Without it, an arch-shaped boundary
  (`14769px2`) fits a meaningless whole-ring centre, invents circles, and
  throws a stray arc outside the silhouette.
- **Never give decal arc candidates a snap tolerance in the render path.**
  Pulling vertices onto the candidate destroyed `14769p0a`'s clock face —
  underside ribs showed through. `shade._decal_arc_candidates` emits the
  candidate only. This is the same hazard as the rim-candidate `NOTE` in
  `hlr._visible_segments_analytic`.
- **`30260p01`'s octagon is the guard for circle recovery** — its 8 vertices
  share a radius, so a circle fits them exactly. Only `ARC_STEP` (45 deg a step
  is too coarse) keeps it a sign. Test pins it.
- **Never `git add -A` in a worktree.** `vendor/` in `.gitignore` matches a
  directory, not the convenience symlink a fresh worktree needs, so `-A`
  commits the link; merging it then checks the symlink out over the real
  directory and a later `reset --hard` deletes the library. That is how the
  pinned 2026-06-27 LDraw snapshot was lost — `complete.zip` serves only the
  latest, so it is gone for good. `/vendor` is now in `.gitignore`; stage
  explicit paths regardless.
- **A long run survives if you DETACH it; chunking was treating the symptom.**
  What kills a run is the tool call's own timeout, not the environment: a
  foreground call dies at its limit no matter what the process is doing, which
  is why "every run short enough to finish inside a tool timeout completed"
  and four longer ones did not. Start it with `nohup … > log 2>&1 &`, then poll
  the log. `BRICK_GOLDENS=full` then finishes unchunked (16 passed, 1051s), and
  so does a 52-case freeze. A killed run leaves a truncated progress bar and no
  summary line, which looks exactly like a run still going — check for the exit
  line before believing either.
- **`BRICK_GOLDENS=1` or the gate does not run — and `=1` is still not the
  gate.** A plain suite reports "N passed, 3 skipped" and those 3 skips are the
  drift tests; two sessions independently mistook that for verification. But
  `=1` renders `3005` ALONE (`--only 3005` in
  `test_frozen_hashes_still_reproduce`), so it passes green through any change
  to any other part. Only `=full` re-renders the 52-case manifest, and it takes
  ~27 minutes. A naive-path change is unverified until `=full` is green.
  `test_drawings_stay_inside_their_own_viewbox` reads the FROZEN json, not a
  fresh render, so it cannot see a fix either until the goldens are re-frozen.

  **And the opposite misread, which cost two sessions an hour of duplicate
  rendering:** `=full` is not "the golden gate" that needs the rest of the
  suite run beside it. `BRICK_GOLDENS` gates `tests/test_goldens.py` and
  nothing else — one `skipif`, confirmed by `grep -rn BRICK_GOLDENS tests/
  scripts/ brick_icons/`. So `BRICK_GOLDENS=full pytest -q` IS the whole suite,
  the same collection a plain run makes, with the drift tests un-skipped rather
  than skipped. There is no "everything except the goldens" run to pair with
  it, and splitting the work that way is pure duplication on a shared machine.
  The variable's scope is one grep; both misreads happened because neither
  session ran it.
- **`goldens.summarize_svg`'s `bbox` is built from path ENDPOINTS** and never
  samples an arc's sweep, so re-splitting arcs moves it with no ink moving. A
  bbox delta is not on its own evidence that geometry moved;
  `scripts/compare-extents.py` reports reported-vs-swept. Correcting the
  measure would re-freeze every `tests/goldens/render/*.json`.
- **Golden rasters are calibrated against the pinned `resvg` 0.47.0.**
  Upgrading it moves every PNG with no engine change; re-freeze deliberately.
- **Arc parameters are DEGREES** across this codebase. OCCT reports radians; a
  missing `math.degrees` draws a full circle as a 6.28-degree sliver, which
  reads as "broken arcs" rather than as a units bug.
- **`occt_faces` catches every exception and returns `[]`.** Two separate
  defects lost whole surfaces for the life of the port with no error anywhere.
  When touching it, re-run with the `except` removed before believing a `[]`.
- **`cmd | tail` buffers everything until exit** and destroys a progress
  stream. Write results with `--out` and let progress go to the terminal.
- **`ls` is aliased to `ls -la` in this shell**, so `$(ls dir/*.svg | head -1)`
  yields a listing header, not a path. It fails silently in a loop — 46
  rasterizations in a row, each "unable to open". Use a glob.
- **Don't `cd` out of the repo in the same command as a `git stash pop`** — the
  pop fails and the work sits in the stash looking lost.
- **A gate that runs green is not evidence it observes what you think.** Three
  gate-shaped holes were found in one day: a wireframe combo that cannot test
  hidden-line removal because it sets `cull=False`, a cel combo that cannot
  move under an engine swap, and an extraction corpus whose candidate pool was
  an alphabetical prefix containing no classic brick, plate or tile. Ask what
  a gate would MISS before trusting it.
- LDView color is not evidence; a proof sheet is not the renderer.

## 2026-09-06 evening: the geometry phase, and what is still unmeasured

On branch `main`, unpushed with everyone else's evening — `git log --oneline @{u}..HEAD` for the current list:

- `9493b33` prefilters the two all-pairs scans in the geometry phase.
  `shade.order_faces` tested every face pair and recomputed each polygon's
  extent inside the test; `occt.select_authored` tested every HLR fragment
  against every locus; `_overlap_witness`'s erosion allocated four padded
  copies per pass. Gated BYTE-IDENTICAL over 120 occt parts and 25 naive parts.
- `454cd51` stops `census-render-diff.sh` running over a dirty `brick_icons/` —
  it swaps files with `git checkout` and had been overwriting whatever another
  session had uncommitted in this shared checkout.
- `2613aeb` adds `measurements.phases` (JSON, SCHEMA_VERSION 6) and a
  `brick_icons.timing` accumulator splitting a render into geometry /
  decoration / fill, exclusive of each other. The census's own `phase` dict was
  already in every JSONL row and being dropped at ingest, so a rebuild
  backfills render/rasterize/truth_mask/compare for both finished runs.

**The performance numbers are not settled, and I have published two that
moved.** What is load- and config-independent, and safe: the byte-identity
gates, and the call counts — 1,253,615 of 10039's 1,279,200 face pairs rejected
at 8.9us each, and 663,145 `_on_locus` calls on 32531b for 279 matches.

The ratios need care, and the trap caught me twice:

1. A *sequential* gate (new revision, then old) measures two revisions and two
   machine states. Mine read 0.90x on a change that alternating passes put
   above 4x. Alternate the sides, min of two.
2. `hlr.visible_segments`'s **default `render_px` is 900; the census renders at
   2048**. A harness that calls it directly measures a render nobody performs.
   Measure through `cli.process_one` with the census's own argv.

Measured through `process_one`, alternating, min of two, on 8 parts from the
census's slow bands (`docs/census-timings/geometry-ab-census-config.log`):
geometry 75.77s -> 15.28s (**4.96x**), whole render 191.63s -> 125.16s
(**1.53x**), geometry falling from 40% of a render to 12%.

**The 1.08x was never a base run.** `census-engine-bench.py`'s 14-part sample
gave that figure because `python scripts/x.py` puts `scripts/` on `sys.path`
and never the checkout root: the venv's editable install then serves
`/Users/mike/src/brick-icons/brick_icons` from inside a worktree, so both
sides of the A/B ran head. `--rev` said `d19f4e4` throughout, because git
resolves that from the cwd. The fingerprint is in the rows — base and head
agree to within noise on every part (0901 0.95 vs 0.79, 32172 1.57 vs 1.56,
44937 3.09 vs 3.04) — and the two 0901 figures were never in conflict: the
bench's 0.95s is a *head* number, next to ab2's head 0.74s. Only ab2 measured
base.
## In flight: mesh refinement, branch `smooth-subdivide` — UNBUILT

Local, unmerged, cut from `bf4ae83`; `git log --oneline bf4ae83..smooth-subdivide`
for what is on it.

The premise, which decides every design call here: a round the library
authored as flat triangles carries no curve for any rule to find, so
**fix the mesh, not the drawing.** Both engines then see one surface, and
strokes and fills come off the same geometry instead of being kept in step by
hand. The declaration to key on is the conditional line: a type-5 across a
facet boundary says the two faces are meant to read as one smooth surface,
and it holds across the cracks that make a dihedral-angle rule wrong here.

`repair.smooth_subdivide` unions facets into declared-smooth patches, takes
corner normals from the patch around each corner, and replaces each facet
with `level**2` triangles on its curved point-normal (PN) patch. A boundary
that is not declared smooth stays on its straight chord, so a refined patch
still meets a flat neighbor along the same line.

**What split a round into N strips was our own quad diagonal, not a missing
declaration.** A type-4 becomes two triangles across the 0-2 diagonal, and no
type-5 line describes that diagonal because the library never had an edge
there — so union-find over declared edges could not cross it, and a quad grid
whose sides are all declared smooth still fell into diagonal staircase
chains. On 28621, 128 of its edges were shared between two "strips" and
carried no condline; there are exactly 128 quads. `flatten` now stamps both
halves of a quad with its id and the refiner joins them: 28621's shoulder
goes from 32 patches of 8 facets to 2 of 128, 3960's dish from 72 of 14 to
424 + 384.

Where the four specimens stand, rendered against `2cedb47`. 4592 draws a
round silhouette and keeps its radial dome gradient — clean. 32062 comes out
byte-identical to an unrefined render, which is what the gate is for. 28621
loses its swirl of overlapping tone fragments and its shoulder silhouette
becomes a true curve instead of a chord chain, but see below. 3960 is worse
than unrefined.

Two conditions gate refinement, both asking only what the library declared. A
patch is refined when it **surrounds a vertex** — one whose every incident
edge is declared smooth — and its edges leave their chords only where the
mesh **pairs** them. The first replaces a triangle-count gate that was a
proxy for it: only at a surrounded vertex is a corner normal the patch's
rather than one chord's, and a patch that is all boundary hands PN a single
facet plane at every corner, so it invents the curve — 32062's axle bevel
pushed past the drawn strokes and left a crescent the fill inked as a
25-vertex sampled boundary. The pairing condition is because bulging one lip
of a crack widens it. The gate is per PATCH and must stay that way: refining
part of one leaves the rest on its chords and cuts it in two for the fill
merge. Over `parts.txt` the surrounded-vertex gate refines every triangle the
count gate did and more (60474 2428 → 2672, 3960 736 → 808), and 32062 none.

**The blocker is un-inked fragments floating on a refined surface**, and it
is one defect on two parts, not a 3960 problem. 28621 carries a single dark
sliver on the shoulder below the stud, with faint pale ghost edges at the
stud base. 3960 carries four dark wedges and a spike on the dome, the same
ghost around the stud, and a sawtooth dark band along the far rim — the band
this repo has fixed once already, so refinement re-triggers a known HLR
failure rather than a new one. Both are unrefined-clean. Scale is the obvious
suspect and the wrong place to start: 28621 refines 256 triangles into 2304
and shows one sliver, 3960 refines 808 into 7272 and shows six.

Rendering against `b0c5d85` (ring/disc axis from its own two columns) and
`2cedb47` (degenerate-ring window, binned gradient stops) changes neither
part's artifacts — checked, not assumed, on all four specimens.

After that: a contact sheet over `parts.txt` against `main`, then the full
suite. Four parts have been looked at (28621, 4592, 3960, 32062).

⚠️ `occt.flatten_part` does its own flatten and does NOT refine, so any test
comparing it against `hlr.visible_segments` compares an unrefined mesh
against a refined one. `test_occt_segments_go_through_the_orphan_cull` broke
exactly that way while an intermediate gate refined 30162. Aligning the two
paths changes the input of 32 occt tests, so it has not been done.

`render.pose_for` is on this branch too and is unrelated to any of the above:
a sticker modelled as a flat sheet (thinnest extent under 1 LDU) is posed
square onto its face rather than at iso. It does not make stickers render —
003238a is still at the wrong scale under naive and raises "no edges" under
occt, both pre-existing.

**Dead ends, measured, do not re-propose:**

- *`shade._seam_edge_mask`'s partial-lie matching.* It matches a mesh edge
  lying anywhere ON a conditional line, where the refiner requires the
  condline to match a facet edge end to end. On 28621 the two tests select
  the SAME 288 mesh edges — zero partial-lie-only ones — and all 320 of its
  condlines land exactly on a mesh edge; 4592 likewise. Only 3960 has any (16
  edges, merging 12 patches). The difference is not what let occt see a
  surface the refiner split.
- *Rejecting a patch that has a face attached to it by a single seam.* Kills
  60474 and 3960 outright, and refines nothing anywhere else in `parts.txt`.
- *Fitting an analytic surface to the patch.* 4592's two big patches fit a
  sphere to 2.44px and everything else worse (plane 45, cone 22, cylinder
  35). No quadric is that surface, and PN triangles do not need one — they
  only need to know which edges are smooth, which the file declares.
- *LDView's `-CurveQuality`.* It only re-tessellates primitive references,
  and this engine already substitutes those with exact analytic surfaces,
  which beats any tessellation. 4592's dome is inline triangles: LDView
  would export the same 180 of them at any quality. There is no
  tessellation knob on our own path — `--curve-quality` feeds LDView alone.
- *Fitting the drawn chords to an ellipse* (`arcfit.fit_silhouette_arcs`,
  landed as `6f042c0`). 4592's one candidate run has no ellipse near it, and
  the gate that makes the pass safe elsewhere only accepts runs that were
  already smooth. It fires on 5 of 74 census parts for a sub-pixel change.
- *Gating on `primitives.from_ref`.* The earlier handoff said to skip
  refinement wherever an exact surface was already substituted. `from_ref`
  substitutes NOTHING on 32062 — `out["analytic"]` is empty — so that gate
  is a no-op on the part it was written for.
- *Carrying the patch id from the refiner into `occt._group_planes`.* Tagging
  each refined triangle with its patch and unioning faces by it took 4592
  from 29 groups to 21, and the drawing was pixel-indistinguishable. It costs
  a face-to-triangle mapping and a field on every plane face. The patches
  have to get coarser before any of that pays.
- *Blaming the cracks, `UnifySameDomain`, or vertex welding.* 28621's 64
  unpaired condline edges are real boundaries, not cracks — the nearest
  same-length edge is over 3 LDU away, and they carry one ancestor face with
  refinement on and off alike. Disabling `UnifySameDomain` leaves the group
  count at 15. Welding vertices at 2e-3 changes no patch on 28621, 4592 or
  3960.

The 128-face fill groups in an unrefined render are the **flat rings** — the
caps, fan-triangulated and chained by the coplanar rule — not the curved
wall. Anything comparing group counts before and after refinement has to
separate the two, or it measures the caps and concludes something about the
round.
