# Redraw requests: a queue the fleet drains, short-circuited locally

For whoever next touches the lightbox's **Redraw** button, the slot rounds
(`refill-slot.sh`, `run-slot.sh`) or `ingest-watch.py`. It answers one question:
when somebody asks for a part to be drawn again, what draws it, and when.

## The request log

A request is one line of `store-queue/requests.jsonl`: part, slot, time, who
asked. It is a file and not a `corpus.db` table because `census-ingest.sh`
rebuilds the database from the render trees, and a request is in no tree.

A request is **pending while its slot holds no render made after it**. Nothing
clears a line: the render landing is the answer, so asking twice is harmless
and a crashed round loses nothing. `brick_icons/requests.py` owns the rule --
`add`, `pending(conn, slot)`, `pending_for(conn, part)` -- and
`scripts/render-requests.py` is its shell face.

## Asking: the lightbox

**Redraw** asks for the slot on screen. The lab looks up what the part last
cost in that slot: its latest attempt, else its latest measurement, else the
slot's mean.

- **Decal, or 20 s or less** (`requests.LOCAL_MAX_SECS`): drawn now, as a lab
  job, on this Mac. It goes through `brick_icons/lab/store.render_into_store`,
  the same function `build-render-store.py` calls, so the lab has no render
  path of its own. The drawing lands in `renders/` and `corpus.db` under a run
  of kind `render`; the lightbox reloads when the job settles. The wall's
  thumbnail stays a bake behind.
- **Anything slower** is appended to the log, and the lightbox says the slot is
  queued for its next round, with the date asked.
- `ldview` and `reference` are drawn outside this repository and refuse a
  request.

## Draining: the next slot round

`refill-slot.sh` puts the slot's pending requests at the front of the list it
launches, ahead of whatever the gap selection picked, and launches even when
the gap itself is empty. It reads requests only through `render-requests.py`,
so replacing the gap selection does not touch the queue.

A requested part is usually already drawn, and the watcher skips drawn parts.
`ingest-watch.py --overwrite-requested`, which `run-slot.sh` always passes,
replaces a drawn part only when it has a pending request. A plain fill round
still never replaces a good row.
