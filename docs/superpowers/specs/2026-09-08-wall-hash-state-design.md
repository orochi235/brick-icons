# The corpus wall's URL hash carries its whole client state

For whoever implements it. It answers: **what goes in the hash, in what
spelling, and what breaks if you restore it at the wrong moment.**

Today `lab/src/corpus/wallHash.ts` carries two fields, `source` and `part`.
Reload the wall and you keep the slot and the open lightbox and lose everything
else: where the camera was, how the grid was sorted and filtered, which cell you
were on. `useParams` already persists `cell`, `gap`, `cols` and `pollMs` to
`localStorage`, so those are not in scope.

## What the hash holds

| field | source |
|---|---|
| `source` | the drawn slot (already carried) |
| `part` | the open lightbox (already carried) |
| `cam` | `View` — x, y, scale |
| `caret` | the picked cell |
| `sort` `filter` `shown` `grouping` `tint` `desc` `excluded` `badges` | the eight `Selection` fields |

**A field at its default is omitted**, in both spellings. An untouched wall
still writes a short hash, and today's `#source=occt&part=3001` links are
unchanged.

## Two spellings, one reader

```
readable   #source=occt&part=3001&cam=1240,880,2.4&sort=year
             &group=category&tint=status&shown=drawn,defect
             &excl=Sticker,%7C&badges=technic&desc=1&caret=4821

condensed  #w=eyJzIjoib2NjdCIsInAiOiIzMDAxIiwiYyI6WzEyNDAsODgwLDIuNF0...
```

`readWallHash` takes either: a `w` key means decode it, anything else reads the
plain params. A legacy link is the readable spelling with most fields absent, so
it keeps working with no compatibility branch.

`wallHashString(state, condensed)` writes one or the other. The choice is a new
`condenseHash` boolean in `useParams`, defaulting false — it sits in
`localStorage` beside `cell`/`gap`/`cols`, gets a checkbox in the PARAMS panel,
and is cleared by that panel's existing `reset`.

## Modules

`wallHash.ts` keeps the state shape, the defaults, `readWallHash` and
`wallHashString`. The base64url codec — compact-key JSON in, URL-safe text out —
is its own file: it knows nothing about the wall and is tested without one.

## Validation

`SAFE` already guards `source` and `part`. Enum fields are checked against
`sortTable()`, `filterTable()`, `CLASS_SPECS` and the tint table, and anything
unrecognized is dropped rather than trusted — a link from an older build then
degrades to the default instead of putting an unknown key into a lookup.
`excluded` and `badges` stay opaque strings, count- and length-capped; they are
only ever compared, never rendered and never used as a path.

## The trap: restore the camera after layout, not at mount

`source` and `part` are read once at first render, from a ref. **The camera
cannot be**: `clampView` would clamp it against a world of zero size and you
would land somewhere other than where you left. It restores once `laid.bounds`
is non-zero.

Camera writes round to integer x/y and 3-decimal scale, and the hash write
debounces about 150ms — `updateCam` fires on every frame of a pan and of a
flick's inertia decay, and `replaceState` must not.

## Tests

- codec round-trips on its own, including non-ASCII
- both spellings round-trip through `wallHash`
- a default-valued field never reaches the string
- `#source=occt&part=3001` still reads
- an unknown enum value drops to its default
- a `CorpusWall` remount restores camera, selection and caret

`CorpusWall.test.tsx` shares one jsdom location across cases and already resets
the hash between them; these cases have to keep doing that.
