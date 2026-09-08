---
name: ingest-ldraw
description: Swap vendor/ldraw for a newer LDraw snapshot and carry across everything derived from it — the parts seed, the features, the render slots, the goldens and each node's copy. Use on "update the LDraw library", "we are on an old parts snapshot", "re-fetch complete.zip", "that part is not in the library", "which parts did the update change", or when a part LEGO released recently has to draw.
---

## Instructions

`vendor/ldraw` is the input everything else is derived from, and it is a
rolling snapshot: `complete.zip` always serves the newest parts update and
nothing serves the one before it. So an update is a migration, not a download,
and the step that cannot be redone is the first one.

The order is: hash the tree you have and keep it, swap, diff, re-derive,
re-render only what moved, re-freeze only what the diff explains, then give
the fleet the same tree.

Getting new drawings into `corpus.db` and onto the wall is `ingest-renders`'s
subject; this file stops at handing it a list of parts.

### 1. Hash what you have, and move it aside rather than over

    .venv/bin/python scripts/ldraw-hash.py --out out/ldraw/<fetched-date>.jsonl
    mv vendor/ldraw vendor/ldraw-<fetched-date>

**Both before anything is fetched.** The 2026-06-27 snapshot was overwritten
in place and is gone; `external-deps.lock` can say what that update did only
because the render slots happened to hold a before.

The manifest is one line per part, and a part is its `.dat` plus every subfile
it resolves to — hashing what the id names calls a subfiled part unchanged,
which is exactly how 50950 moved in that update. It reads only what the
renderer reads (types 1-5, and type-0 `BFC`), so an update that rewrites
headers across thousands of files costs nothing. 24,591 parts in 3m47s here,
against the fleet-hours a re-render costs.

The old tree is 612 MB. Keeping it is what lets you draw the old library at
HEAD — a stored render is a before for the old library *and* an older engine
at once, and cannot separate them.

### 2. Fetch, then put back what the download does not carry

    ./scripts/setup-ldview.sh

It fetches only when `vendor/ldraw/parts/3001.dat` is absent, so it does
nothing against a tree that is still there and the whole job against one that
has been moved aside. It `rm -rf`s `vendor/ldraw` before unzipping.

**`Unofficial/` was fetched by hand and no download recreates it:**

    cp -R vendor/ldraw-<fetched-date>/Unofficial vendor/ldraw/

The official release ships 2374b and 5241 referencing subparts it does not
contain — never promoted off the Parts Tracker — and `hlr.flatten` drops a
reference it cannot resolve without a word. Before those three files were put
there, 2374b lost all four mirrored corners and 5241 its whole shell, in every
slot, and our own engine never said so; the browser bake is what noticed.

The scan that catches this rides along with the manifest run: `ldraw-hash.py`
names every part referencing a file the library cannot resolve. **Zero is the
expected number** — it is what the tree reads today.

Then record the fetch in `scripts/external-deps.lock`: `source`, `fetched`,
`dat-files`, and the `manifest-sha256` the recipe in that file computes. It is
the only place the snapshot has a name.

### 3. Ask what changed, before re-deriving anything

    .venv/bin/python scripts/ldraw-hash.py --out out/ldraw/<new-date>.jsonl
    .venv/bin/python scripts/ldraw-hash.py --diff out/ldraw/<old>.jsonl out/ldraw/<new>.jsonl

`added`, `dropped`, `moved`. **`moved` is the re-render list and it is short** —
the last update moved one part of the 54 render cases it was checked against.
Every step below is scoped by it, and the alternative to having it is
re-rendering 24,591 parts to find out.

### 4. Re-derive the database

A full rebuild reseeds parts and features from the library and reindexes every
render, so it is the route. Temp file and swap, and read `ingest-renders`
first for why:

    tmp=corpus.db.ingest.$$
    .venv/bin/python scripts/build-corpus-db.py --out "$tmp"
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);"
    rm -f corpus.db-wal corpus.db-shm && mv -f "$tmp" corpus.db

(`part-features.py --build` replaces `part_features` in place, which is the
route when the extractor moved and the library did not. It is not this one.)

Two things the rebuild loses quietly, both on the `dropped` list:

- **A status a human set on a dropped part is gone.** `import_statuses` is
  `UPDATE parts SET ... WHERE id=?`, so a row for an id the library no longer
  ships matches nothing — and the count it returns still includes it. Cross
  `dropped` against `tests/goldens/part-status.toml` by hand. Defect rows
  survive: `defects` names a part id and nothing enforces that it exists, so
  they dangle rather than vanish, which is the better failure of the two.
- **An `added` part has no years, no set count and no successors.** Those come
  from Rebrickable, not from the library, so it carries none of the wall's
  `retired` / `popular` / `obscure` tags until `scripts/fetch-part-years.py`
  runs again and rewrites its two committed CSVs.

### 5. Every stored render is now stale, and nothing in the database says so

`renders.sha256` hashes the file on disk, so a drawing made against the old
library still verifies perfectly after the swap; no column records which
snapshot drew it. The `moved` list is the only instrument there is.

Re-render `moved` against each slot that holds those parts, then reindex and
bake:

    .venv/bin/python scripts/build-render-store.py --sources occt --force <parts...>
    .venv/bin/python scripts/index-slot-renders.py --source occt --force
    .venv/bin/python scripts/bake-thumbs.py --source occt > out/bake.log 2>&1

**Every `--force` there is load-bearing, and each guards a different cache.**
Without the first, a part already holding a file under `renders/<source>/` is
reported `present` and never drawn; and the lab's render cache is keyed on
argv alone, so even a part with no file comes back as the drawing the old
library made. Without the second, a part already recorded under that source is
skipped and the row keeps the old sha.

`render-corpus-batch` fills a slot's *gaps* and will not see these parts —
they have a render, it is merely wrong. A `moved` part's census measurements
are wrong for the same reason: they score a drawing of geometry that is no
longer there.

### 6. Goldens: re-freeze on the diff, never on the gate

    BRICK_GOLDENS=full .venv/bin/python -m pytest tests/test_goldens.py

Run it **before** the swap as well, so a red gate afterwards is attributable.
`hashes.txt` is an exact byte lock on the naive engine and `decal-hashes.txt`
the same for decal extraction. A golden part on the `moved` list fails by
construction; a golden part that is *not* on it and fails anyway is a finding
about the engine, and re-freezing is the wrong response.

`scripts/freeze-goldens.py` writes the render seam by default and needs
`--seam extraction` for the decal half, so re-freezing one is not re-freezing
both. Name the moved parts in the commit message either way: a re-freeze that
does not say which parts the library moved is indistinguishable from
laundering a real drift.

### 7. The fleet gets the same tree, or its rows are not comparable

`vendor/` is gitignored, so `onto sync` never carries the library: each node's
copy was rsynced by hand and is its own snapshot. A node still on the old one
writes measurements nothing can compare, and no row says which library drew
it. `census-round` step 5 asks the nodes to agree on the snapshot; this is
where that is made true.

A node's tree is `~/.config/onto/work/brick-icons`, and `onto run --in
brick-icons <node> -- pwd` is how to confirm that rather than assume it. Not
every node holds a library at all: keiei has no `vendor/ldraw` and can render
nothing.

**Check `onto jobs` before rsyncing to a node.** Replacing `vendor/ldraw`
under a running census swaps the geometry mid-job, and the rows on either side
of that moment are indistinguishable afterwards.

Verify by the manifest sha from `external-deps.lock`, computed on the node —
not by the rsync exiting 0.

### 8. Report what moved and what is still stale

The counts from step 3, which slots were re-rendered, which goldens were
re-frozen and for which parts, and which nodes have the new tree. **A part on
the `moved` list that has not been re-rendered is a wrong drawing on the wall
that nothing else will ever flag** — there is no gate for it, which is why it
belongs in the report.

## Not covered here, and wanted

**Nothing records which snapshot drew a render.** `runs` carries a commit sha
and arguments; neither the run nor the render row carries the library. Two
slots half re-rendered across an update are indistinguishable from two slots
that agree, and the manifest diff only tells you which parts *could* be wrong.

**The manifest is as losable as the tree.** It is written under `out/`, which
is gitignored, so the record of what the library held before the swap survives
exactly as long as this machine's scratch does — which is the failure that
lost the 2026-06-27 snapshot in the first place. 2.9 MB per snapshot;
committing it, or a shortened form of it, is a call nobody has made.
