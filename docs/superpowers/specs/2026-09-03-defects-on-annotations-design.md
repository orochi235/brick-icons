# Defects on labkit annotations

**Replaces the lab's hand-rolled mark layer with `@weasel-js/labkit`'s
annotations capability. Unbuilt.**

For whoever implements this. It assumes you know the part inspector and its
panes, and nothing about labkit's annotations API — which is new in
`@weasel-js/labkit@1.4.0-pre.0`, already pinned in `lab/package.json`.

**The question this answers:** the lab draws defect marks with its own overlay,
its own geometry math and its own staleness rule. labkit now ships all three.
What comes out, what stays, and where a defect lives afterward.

## What a mark is, in labkit

An *instrument* (the part inspector) declares an `annotations` capability naming
*targets* — regions that accept marks. A target is a pane. Each target gets its
own weasel scene; a mark is a node in it, and its id is `<target>/<node>`.
Positions are stored as fractions of the target's content box, which is the form
the lab already stores. `positionDependsOn` names the config keys whose change
invalidates a stored position, and `isStale(mark, config)` answers against them.

## What goes, what stays

Deleted: `src/defects/MarkLayer.tsx`, `MarkLayer.css`, `geometry.ts` and their
tests. labkit's overlay draws marks, its `frac.ts` does the coordinate math, and
its palette replaces the `armed` boolean.

`identity.ts` keeps `slug` and `defectId` — minting human-readable defect ids has
nothing to do with position — and loses `SEEN_KEYS`, `Seen`, `seenFrom` and
`seenMatches`. `positionDependsOn: ['angle', 'shading', 'shade_style']` is
`SEEN_KEYS` exactly, and `isStale` is `seenMatches` negated. If the staleness
half survives this migration, labkit's API is wrong somewhere.

Unchanged: `useDefects.ts`, `DefectList`, `DefectCard`, `FileDefectDialog` and
their tests. New: `src/defects/projection.ts`, the only added file.

## Three decisions, and what they rule out

**The server stays the record of truth.** labkit's store holds marks in memory;
the lab projects `Defect[]` into it on load and writes back through
`client.addDefect` / `client.patchDefect`. Declaring `annotations.storage`
instead is the obvious answer and will be re-proposed: it deletes the sync layer
and makes weasel history the undo authority. It was declined because
`SerializedAnnotations` is `{ version, scenes: Record<target, unknown> }` —
opaque serialized scenes — so the Python server would store a blob it cannot
read, and `/api/defects?part=`, the cross-part `DefectList` and every
server-side report go blind. `AnnotationStorage.load` is also synchronous, and
`LabClient` is not.

**A defect filed against both engines draws on both panes.** One mark per
(defect, engine), joined by `meta.defectId`. Comparing the same region across
engines is the inspector's point. The fan-out costs nothing because the server
is the truth: an edit goes to the server and the reload re-projects every pane.

**`Defect.mark` keeps its shape and gains two optional siblings**, `kind` and
`points`. A stored defect with no `kind` reads as a rect, so nothing needs
migrating. This mirrors `Annotation`, which carries `frac` as the bounds always
and `points` only for kinds a box cannot describe.

## The declaration

```ts
annotations: {
  targets: (state, config) => markablePanes.map((s) => ({
    id: `pane:${s.id}`,
    ref: paneRefs[s.id],
    content: { w: renderPx(config), h: renderPx(config) },
    view: cameraRef.current,
    positionDependsOn: ['angle', 'shading', 'shade_style'],
    base: () => paneBase(s.id),
  })),
  meaning: { statuses: STATUSES.map((id) => ({ id, label: id })) },
}
```

`markablePanes` is the sources whose `paneSpec` sets `marks: true` — the engine
and diff panes. The 3D pane has `marks: false` and stays out.

**`targets` is handed only `(state, config)`, so it cannot reach the camera.**
The pane camera lives in `ctx.trial.view`, which is the trial's, not the
instrument's. Hold it in a ref that `render` keeps current and read
`cameraRef.current` here — labkit calls `targets` afresh on every relevant call
rather than caching it at construction, so a ref is read live. Do not mirror the
camera into instrument state; that duplicates a value labkit already owns and
the two will drift. A target that omits `view` gets a fit rather than the
identity, so leaving it off does not fail loudly — marks simply stop tracking
pan and zoom, which no jsdom test can see.

Capture needs no new work. A pane's `PaneState` is already either
`{ kind: 'svg', markup }` or `{ kind: 'image', src }`, and `CaptureSource` takes
exactly those two shapes, so `base()` forwards the state it already holds. An
SVG base keeps the export vector all the way through.

## Data flow

Load: `useDefects` fetches `Defect[]`; the projection adds one mark per
(defect, engine in a declared target), carrying `defectId` in `meta`.

Draw: the mark exists in labkit's scene with no `defectId`. That is the signal to
open `FileDefectDialog`. On submit, `buildDefect` mints the record, the client
files it, the reload re-projects, and the unfiled mark is replaced by projected
ones.

Edit, status, delete: through the server, then re-project. `DefectCard` and
`DefectList` keep calling `setStatus` as they do today.

`subscribe(fn)` carries no change payload by design, so the projection diffs
snapshots to notice a new, moved or removed mark.

## Where ownership changes hands

An unfiled mark belongs to labkit: drawn, draggable, and Cmd+Z takes it back.
Filing hands it to the server, and from then on it is projected rather than
owned. So weasel history never has to model a server write, and undo never
diverges from what is stored.

## Server change

`Defect` gains optional `kind` (`'rect' | 'line' | 'arrow' | 'ellipse' |
'stroke' | 'text'`) and `points` (`{ x, y }[]`, absent for a rect). No migration;
existing records read as rects.

## Testing traps

jsdom cannot see the overlay — it renders through a portal into labkit's shared
GL surface. Three things need a real browser, and a green jsdom suite means
nothing about any of them: a mark landing on the correct pane rather than every
pane, the stale dash, and a line drawn as a line rather than as its bounding box.

`geometry.test.ts` and `MarkLayer.test.tsx` die with their subjects; their
coordinate round-trip coverage is now labkit's. `identity.test.ts` keeps its
slug and id cases and drops its seen cases. New coverage is the projection
round-trip: `Defect[]` in, marks out, and a drawn mark back to a `Defect`.

Preserve deliberately: the cross-hook same-part notification in `useDefects`
(filing in one pane refreshes the defects panel), id collision suffixing, and
the status sort and filter in `DefectList`.

## What this is meant to prove

Arc 5 exists to test arc 3's API against a real consumer. Three frictions are
already visible and belong back in weasel's spec once this lands:

- `subscribe()` carries no delta, so every consumer diffs snapshots.
- `AnnotationStorage.load` is synchronous, which makes the storage hook
  unusable against any real backend and forces the projection above.
- `targets(state, config)` cannot see the trial view, so a target that wants to
  track its pane's camera has to smuggle it through a ref.
