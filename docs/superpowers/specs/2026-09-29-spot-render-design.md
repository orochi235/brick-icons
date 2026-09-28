# On-demand spot rendering

**Status: designed 2026-09-29, not built.** Three pieces, in build order: onto
service jobs (onto repo), the `brick-spot-render` worker and redraw path
(brick-icons), and per-cell refresh on the wall (pezlie and the lab).

For whoever builds or reviews this: how the lab's **Redraw** button draws a
part on the fleet within seconds and swaps the new drawing into the lightbox
and the wall cell without a reload.

## What it replaces

Today **Redraw** takes one of two paths, split by an estimated cost
(`LOCAL_MAX_SECS = 20` in `brick_icons/requests.py`):

| estimate | today |
|---|---|
| ≤ 20s, or any decal | the lab server draws it on this Mac, in-process |
| > 20s, or no cost on record | one line in `store-queue/requests.jsonl`; drawn only when someone runs `scripts/refill-slot.sh` |

Both go. Every redraw goes to one warm worker on the fleet, and nothing renders
on this Mac. The cost split, the local render path and the lazy queue are
removed. `requests.jsonl` remains as a record of what was redrawn, when, and at
which build.

## Flow of one redraw

```
Lightbox "Redraw"
  → POST /api/corpus/redraw {part, source}          lab API, this Mac
  → onto call brick-spot-render {part, source, argv, build}
      worker: engine already imported, at the requested build
      ← {svg, secs, build, state, error}
  → db.store_render (+ attempts row)                existing path; review queue still logs displacements
  → thumbs.bake_part + thumbs.patch_cell            that part's tiles, and its box in sheet-8 / sheet-32
  → server-sent event: changed {part, source, sha, sheet_version}
Browser: lightbox and wall cell both switch to the new sha
```

A second click on the same part and slot while one is in flight joins it,
through the lab's existing single-flight helper.

## onto: service jobs

onto has no way today to hand work to a running process: jobs are one-shot, a
running job's stdin is not connected, and a running job locks its tree against
sync. This adds a job kind that stays up and takes requests.

- `onto service up <name> --in <tree> [--prefer <node>] -- <cmd>` starts it,
  with no job-length cap, and restarts it if it exits.
- `onto call <name> <json>` sends one request through the node agent, over the
  same authenticated TLS every other onto call uses, and returns the reply. No
  new port is opened on the node. The route follows the pattern of the existing
  `POST /v1/jobs/{id}/lease`.
- A request may carry the commit the caller expects. If the service is on
  another, onto rolls it: sync its tree to that commit, restart, then deliver.
  The service never updates itself.
- `onto service ls` and `onto service down <name>`.

## brick-icons: the worker

`brick_icons/spot_worker.py`, started as

    onto service up brick-spot-render --prefer studio --in brick-icons-spot \
      -- .venv/bin/python -m brick_icons.spot_worker

- **Node.** It prefers studio, and falls back to any other node with a
  provisioned tree, never this Mac.
- **Tree.** It has its own, `brick-icons-spot`, so it never holds the
  `brick-icons` tree that census and fill jobs sync into.
- **Warm.** It imports the engine once, then answers each request with a
  `cli.process_one` call in the same process. It runs a small pool, 2 workers
  by default, with the batch per-part timeout (`RENDER_TIMEOUT_S`).
- **Build.** Every request carries origin/main's build, so a redraw right after
  a push pays one roll. Unpushed local changes can't be spot-rendered; they
  stay on the CLI.
- **Reply.** It returns the SVG, seconds taken, build, and state or error. The
  lab computes the sha itself.

## brick-icons: the lab API

- `POST /api/corpus/redraw` calls the service, ingests the reply with
  `db.store_render`, and writes an `attempts` row carrying the seconds taken,
  so cost history stays true. `store_render` writes no `attempts` row itself;
  that write is new.
- `thumbs.patch_cell(source, part)` pastes the part's freshly baked 8 and 32 px
  tiles into its box in `sheet-8` and `sheet-32`, with the edge replication
  `compose` already does, and writes each sheet atomically. The sheet version
  becomes a counter in the manifest rather than the file's mtime in whole
  seconds, which two writes within one second would share.
- `GET /api/events` streams server-sent events. It carries `changed` for now,
  and can later replace the 10-second cell poll.
- `reference-gray` and `reference-lines` join `DRAWN_ELSEWHERE`, so a redraw
  of a reference slot is refused like the others.

## pezlie and the lab: one cell refreshes

This is the Wall page (`/wall`, pezlie's `WallView`).

- The data store takes the cell's new `sha` through the existing
  `ItemStore.patch`, so the cell's state and colors update.
- A new public spec field, `thumbKey` (for brick-icons, `'item.sha'`), names
  what identifies a cell's image. pezlie's tile and SVG caches key on it. When
  a cell's key changes, the wall redraws that cell's 8 and 32 px tiles into its
  copy of the sheet and refetches its 128 px tile and SVG, without reloading
  the whole sheet. This is a public field in a pezlie minor release, not a
  reach into its internals.
- The lab's own image caches key on the same sha.
- The lightbox also listens to `/api/events`, so an open lightbox updates
  whatever triggered the redraw.

## Failures

| failure | the lab shows | what happens |
|---|---|---|
| service down or unreachable | "spot render is down" on the button, and a line in `brick-lab stat` | nothing is queued; the click fails in under a second |
| service rolling to a new build | "updating worker…" | the request waits up to 30s, then fails with the roll's error |
| part times out or the engine raises | "Redraw failed: timed out", or the error text | an `attempts` row records it; the stored drawing is untouched |
| new drawing identical to the stored one | "unchanged" | no sheet patch and no event; `made_at` is refreshed |
| sheet patch fails | a warning in the API log | the drawing is stored; the next full bake repairs the sheet |
| browser misses an event | nothing | the 10-second cell poll still picks up the new sha |

## Testing

- **onto:** service start, restart after a crash, roll to a new commit, and a
  `call` round trip, in its own Go tests.
- **Worker:** a request returns the same SVG bytes as the CLI given the same
  argv.
- **Lab API:**
  - the redraw route against a stub `onto call`, covering every row of the
    failure table;
  - `patch_cell` changes only that cell's box, pixel for pixel;
  - one `changed` event per stored redraw.
- **pezlie:** a changed `thumbKey` refetches only that cell.
- **End to end:** run once, headless, against the studio worker. Redraw
  612p01, and the lightbox and wall cell both change without a reload.

## Not in scope

More than one worker, batch redraws from the UI, and redrawing reference slots.
