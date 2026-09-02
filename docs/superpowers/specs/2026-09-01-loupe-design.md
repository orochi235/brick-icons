# The loupe

For whoever next touches `lab/src/panes/`. It answers: how does a magnifier
follow the cursor across panes without disturbing the camera they share, and
where does the magnified drawing come from on each kind of pane?

Hold Alt over a pane and a circular bubble follows the cursor, showing that
pane's drawing magnified. The shared camera does not move, so the whole part
stays in view behind it. Release and it is gone. The panes already zoom to 64x
together; what the loupe adds is detail *without* losing the frame.

## The magnified camera is the shared camera

`camera.zoomAt(camera, factor, sx, sy)` scales about a screen point and keeps
the world point under it fixed. That is exactly the loupe's transform: the
bubble draws the same stage at `zoomAt(camera, factor, cursor)`, clipped to a
circle centred on the cursor. No second projection, and the fixed-point rule is
already under test in `camera.test.ts`.

One difference, and it is the trap: the loupe clamps at 1024 rather than
`MAX_ZOOM`. Reusing the 64 clamp makes the bubble silently stop magnifying once
the shared camera is near its own limit, which reads as the loupe being broken.

## Where the magnified drawing comes from

`SourcePane` inlines its stage today. Extract `PaneStage` — `{state, camera,
busy}` to the transformed div — and render it twice, once normally and once
inside the bubble. The SVG panes then magnify as vectors rather than as pixels,
because the bubble holds the same DOM at a larger scale.

The 3D pane cannot be cloned that way: a WebGL canvas draws from a framebuffer,
not from markup. So it supplies its own copy. The r3f canvas runs at a
supersampled backing store on `frameloop="demand"`, and the pane captures it to
a bitmap whenever the scene changes — pose, part, style, or shared camera. The
bubble windows into that bitmap like any image pane, and goes soft past the
supersample factor.

**The snapshot covers the whole pane, not the loupe's frustum.** Rendering the
loupe's frustum would be sharp at any factor and is the obvious alternative; it
is wrong here because the frustum moves with the cursor, so every pointer event
invalidates the cache and the "seldom" that justifies caching is gone.

## Reach

Default: the bubble is on the pane under the cursor. A toggle mirrors it to the
same body-relative point on every pane that shares the render's fit — the
engine panes and the diff, which draw one viewBox at one size, so one body
coordinate is one world point across all of them.

The reference pane is LDView with `-AutoCrop=1` and the decal is a flat carrier
rather than a view of the part. Neither shares that fit, so neither mirrors.
Both still magnify normally under the cursor.

## Controls

Alt held is the whole interaction: the bubble appears, and the wheel adjusts the
factor instead of the shared zoom. Nothing is taken from pan, zoom or mark,
and there is no mode left armed by accident.

Alt governs the wheel whether or not the loupe is sticky. So with the button on
and no key held the wheel still zooms the shared camera, and the factor is only
ever changed deliberately.

A `loupe` button sits in the pose bar beside `mark`, because a modifier nobody
is told about is a feature nobody finds. Its tooltip names the key, clicking it
makes the loupe sticky — up without the key held — and it lights while the
loupe is live either way.

`loupe_factor` (2–16, default 6), `loupe_sticky` and `loupe_all_panes` are
`LAB_ONLY` keys, so they persist with the trial and stay out of `renderConfig`.

With `mark` armed the loupe still shows and the drag still marks. The bubble
occludes part of what is being dragged over; that is accepted rather than
solved.

## Modules

- `panes/loupe.ts` — pure. The magnified camera, the bubble's geometry, and
  which panes mirror. Tested the way `camera.ts` is.
- `panes/useLoupe.ts` — Alt state and the sticky toggle, one hook for every
  pane so they agree on whether the loupe is live.
- `panes/PaneStage.tsx` — extracted from `SourcePane`, rendered twice.
- `SourcePane` — a `loupe` prop; draws the bubble when it is non-null.
- `ThreePane` — the supersampled snapshot and its invalidation.
- `chrome/PoseBar.tsx` — the button.

Bubble diameter is 40% of the pane's shorter side, clamped to 120–320px.

## Out of scope

**Clone this view** — a second inspector with its own camera — is the other
answer to inspecting a detail without losing the whole, and it is a separate
piece of work: it touches trial and view ownership rather than the panes. Build
it after, with what the loupe teaches.
