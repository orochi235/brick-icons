# On-demand spot rendering

**Status: built and merged (main a68d64b); the worker is up on studio.**
Three pieces: onto service jobs (onto repo, released in onto be0cf2f), the
spot render worker and redraw path (brick-icons), and per-cell refresh on the
wall (pezlie ^0.4.0, and the lab). What is left -- the sheet masters and the
end-to-end check in the lab -- is `docs/superpowers/plans/2026-09-29-spot-render.md`.
The flow below is as built; where the build departed from the design, the
design text was corrected rather than kept.

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
removed, and so is everything that read the queue: `requests.pending` and its
helpers, `scripts/render-requests.py`, the front-loading in `refill-slot.sh`,
`ingest-watch.py --overwrite-requested` (which `run-slot.sh` passed by
default), and the lightbox's "Queued for the next round" note.
`requests.jsonl` remains as a record of what was redrawn, when, and at which
build; the review queue still links a displaced drawing to the ask behind it.

## Flow of one redraw

```
Lightbox "Redraw"
  → GET /api/spot                                   is the worker up, and at origin/main?
  → POST /api/corpus/redraw {part, source}          lab API, this Mac
  → onto call --commit <origin/main sha> brick-spot-render {part, source, argv, build}
      worker: engine already imported, rolled to that commit if it was elsewhere
      ← {svg, secs, build, state, error, detail}
  → db.store_render + an attempts row               the review queue still logs displacements
  → thumbs.bake_part                                that part's tiles and masks, before anything is announced
  → server-sent event: changed {part, source, sha, build}
  ← the POST answers
  → in the background, one slot at a time:
      thumbs.patch_cell                             its box in sheet-8 / sheet-32, and their masks
      server-sent event: sheets {part, source, versions}
Browser: the lightbox reloads the part; the wall polls its feed and redraws that cell
```

The tiles are baked before `changed` because the wall fetches them under the
new sha as soon as it hears, and a tile fetched early is cached, old or
missing, under that key for good. The sheet patch, seconds of master and WebP
writes (measured below), is the only step that runs behind. No page listens
for `sheets`: the wall draws the new cell from its tiles, and the patched
sheets serve the next fresh page load.

A second click on the same part and slot while one is in flight joins it,
through the lab's existing single-flight helper.

## onto: service jobs

Built; onto's guide is `site/src/content/docs/guides/services.mdx` in the onto
repo. What brick-icons relies on:

- `onto service up <name> --in <tree> --prefer <node> [--env K=V] -- <cmd>`
  keeps a process up with no deadline and restarts it when it exits. The tree
  must already be on the node (`onto sync --in <tree> <node>` first).
  `onto service ls` and `onto service down <name>` list and stop it.
- `onto call [--timeout <dur>] [--commit <sha>] <name> [<json> | -]` sends one
  request and prints the reply. Exit 0 is a reply; 65 a bad request; 69 down
  (no service, or its node unreachable within a second); 75 the process died
  mid-request (it is restarted, and one retry is safe); 78 the roll failed;
  124 no reply in time. The reason is on stderr.
- `--commit` takes a hex sha on the tree's origin, never a ref. When the
  service is elsewhere, onto rolls it: in-flight calls finish, the tree is
  reset to the commit (untracked files removed, ignored ones kept), and the
  process restarts. Installing a changed dependency is the process's job.
- The process gets newline-delimited JSON on stdin: the caller's fields plus
  onto's `"id"`. Each reply is one JSON line on stdout echoing that id, in any
  order, several in flight. Non-JSON stdout and all of stderr go to the job
  log.

Measured by onto: a 134 ms round trip, a 1.1 s roll, and a down exit in 40 ms.

## brick-icons: the worker

`brick_icons/spot_worker.py`, started through `scripts/spot-worker.sh` as

    onto service up brick-spot-render --in brick-icons-spot --prefer studio \
      -- scripts/spot-worker.sh

- **Node.** It prefers studio, and falls back to any other node with the
  tree, never this Mac.
- **Tree.** It has its own, `brick-icons-spot`, so it never holds the
  `brick-icons` tree that census and fill jobs sync into. Provisioning it is
  `onto sync --in brick-icons-spot studio`, then an APFS clone of `.venv` and
  `vendor/ldraw` from the node's provisioned `brick-icons` tree. Both are
  ignored by git, so a roll keeps them.
- **Start.** `scripts/spot-worker.sh` refuses a tree without `vendor/ldraw`,
  runs `uv sync`, then starts the worker. onto runs it again after every roll.
- **Warm.** It imports the engine once, then answers each request with the
  CLI's own render path in the same process tree. It runs a pool of 2 by
  default, each render in a forked child under the batch per-part timeout
  (`RENDER_TIMEOUT_S`).
- **Build.** Every redraw names origin/main's commit, so a redraw right after
  a push pays one roll. Unpushed local changes can't be spot-rendered; they
  stay on the CLI.
- **Reply.** It returns the SVG, seconds taken, its build, and either a state
  (`drawn`, or `none` for a decal with nothing to draw) or an error: the
  exception's type name and its message as `detail`. The type name is what
  the wall reads (`TimeoutError` is a state of its own). The lab computes the
  sha itself.

## brick-icons: the lab API

- `POST /api/corpus/redraw` calls the service, ingests the reply with
  `db.store_render`, and writes an `attempts` row carrying the seconds taken,
  so cost history stays true. `store_render` writes no `attempts` row itself;
  that write is new. Each redraw gets its own run, of kind `store` with
  `dir` `out/store/spot`: a rebuild carries across only store runs' attempts,
  and the newest run is what reads as a part's latest attempt. Every outcome
  is a `state` in the answer (`stored`, `unchanged`, `none`, `failed`,
  `down`); only a refused ask is an HTTP error.
- `GET /api/spot` answers `up`, `stale` or `down` from a ping sent without a
  commit, so asking never rolls the worker. `stale` means the worker is on
  another build than origin/main, and is how the lightbox knows to say
  "updating worker…" before it posts: the POST itself only returns at the end.
- `thumbs.patch_cell(source, part)` pastes the part's freshly baked 8 and 32 px
  tiles into its box in `sheet-8` and `sheet-32`, with the edge replication
  `compose` already does. It edits a lossless master kept beside each sheet
  and re-encodes the WebP from it: one decode and re-encode of the occt slot's
  sheet-32 WebP changed 8.7M of its 32M pixels (measured 2026-09-28), so
  patching the WebP itself would degrade every cell a little on each redraw.
  The master is a PNG at compress level 1, 32 MB and 0.7 s to write for
  sheet-32, plus 3.2 s to encode the WebP. Every write is atomic, and a lock
  keeps a bake and a patch off the same slot at once.
- The sheet version becomes a counter in the manifest rather than the file's
  mtime in whole seconds, which two writes within one second would share. It
  is `max(previous + 1, unix seconds)`, so a slot wiped and rebaked never
  reuses a version a browser has cached.
- `GET /api/events` streams server-sent events: `changed` and `sheets`. It
  can later replace the 10-second cell poll. The lab serves on a
  `uvicorn.Server` subclass that ends open streams as shutdown begins, since
  uvicorn waits on open responses before the lifespan's exit runs.
- `reference-gray` and `reference-lines` join `DRAWN_ELSEWHERE`, which becomes
  every slot `db.is_reference_slot` names, so a redraw of a reference slot is
  refused like the others and a new one needs no second list.
- The lab API's launchd agent gets `~/.local/bin` on its PATH, where `onto`
  lives; without it the lab could never call the service.
- The part detail's `build` for a slot comes from the spot run when the slot's
  render came from one, since a spot redraw files no measurement.

## pezlie and the lab: one cell refreshes

This is the Wall page (`/wall`, pezlie's `WallView`), on pezlie ^0.4.0.

- pezlie keys cell images on the existing `item.sha` (`imageKey(item)` is
  `id@sha`, and tile and SVG URLs carry `shaVersion(sha)`). brick-icons adds
  nothing to its spec; there is no separate `thumbKey`.
- On a batch of `changed` events for the slot on screen, the lab calls
  `WallHeader.poll()`, which asks `fetchItems(slot, since)` for changes at
  once. The delta carries the new sha because `record_render` stamps
  `indexed_at`, which the cells feed reads. The data store takes it through
  `ItemStore.patch`, and the cell's state and colors update.
- When a poll moves a sha, the wall refetches that cell's 128 px tile and SVG
  and draws its per-level tiles (`thumbs/<slot>/<level>/<id>.webp`, which
  `bake_part` writes) into its in-memory sheets. It never refetches a sheet;
  `patch_cell` is for the next fresh page load.
- Each poll that moves a sha copies every sheet level once, the 32 px one
  about 110 MB transiently (pezlie's estimate), so the lab batches events:
  the first starts a quarter-second window and the whole window is one poll.
- `/corpus` is retired, so nothing refetches a sheet after a redraw; its
  loose and vector thumb caches went with it.
- The lightbox also listens to `/api/events`, so an open lightbox updates
  whatever triggered the redraw.

## Failures

| failure | the lab shows | what happens |
|---|---|---|
| service down or unreachable | "spot render is down" on the button, and a line in `brick-lab stat` | nothing is queued; the click fails in under a second |
| service rolling to a new build | "updating worker…" | the request waits for the roll, then draws |
| roll failed (exit 78) | "Redraw failed: updating worker failed:" and onto's stderr | the worker stays up on its old tree; nothing is recorded |
| worker process died mid-request (exit 75) | nothing, the first time | retried once; a second death fails as `ProcessDied` |
| part times out, `onto call` times out (exit 124), or the engine raises | "Redraw failed: timed out", or the error text | an `attempts` row records it (an `onto call` timeout with the call's timeout as its seconds); the stored drawing is untouched |
| new drawing identical to the stored one | "unchanged" | no sheet patch and no event; `made_at` is refreshed |
| tile bake fails | a warning in the API log | the drawing is stored and `changed` still sent; the next bake repairs the tiles |
| sheet patch fails | a warning in the API log | `sheets` is sent for whichever sheets did patch; the next full bake repairs the rest. A slot baked before the lossless masters refuses every patch until `scripts/bake-thumbs.py` rebakes it |
| browser misses an event | nothing | the 10-second cell poll still picks up the new sha |

## Testing

- **onto:** service start, restart after a crash, roll to a new commit, and a
  `call` round trip, in its own Go tests.
- **Worker:** a request returns the same SVG bytes as the CLI given the same
  argv; two requests draw at once; a timeout and an engine error are replies.
- **Lab API:**
  - the redraw route against a stub of the `onto call` adapter, covering every
    row of the failure table, and the adapter against a fake `onto`;
  - `patch_cell` changes only that cell's box, pixel for pixel, and matches a
    full compose;
  - one `changed` event per stored redraw, heard only once the part's tiles
    are on disk.
- **pezlie:** its own tests.
- **End to end:** run once, headless, against the studio worker. Redraw
  612p01, and the lightbox and wall cell both change without a reload.

## Not in scope

More than one worker, batch redraws from the UI, and redrawing reference slots.
