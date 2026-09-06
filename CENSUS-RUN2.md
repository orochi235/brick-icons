# Census run 2 — what is running and where

**What this is:** the state of the silhouette census as of 2026-09-05 13:45, across two nodes.
**Who it's for:** whoever picks this up next, in this repo. Assumes `HANDOFF.md` for what the
census measures; this file only carries what changed today.

**The question it answers:** run 1 measured 13,928 parts and saved no drawings. What replaced it?

## Where coverage actually stands — ask the script, not this file

    .venv/bin/python scripts/census-coverage.py            # the table
    .venv/bin/python scripts/census-coverage.py --out out/census/todo

Every part list in this file was cut at 13:44 on 2026-09-05 and the run that followed changed
the answers. The script derives coverage from `corpus.db` instead, so it cannot go stale, and
`--out` writes each bucket as a plain list for `--list`. As of 2026-09-06 01:30, over the
8,235-part corpus:

| | drawn | redraw | fails |
|---|---|---|---|
| naive | 4,789 (58%) | 1,837 | 1,609 |
| occt | 2,653 (32%) | 4,168 | 1,414 |

**Three buckets, three different jobs.** *drawn* has a render on disk and indexed. *redraw*
measured fine and kept no drawing — a render pass, costed from each part's own recorded timing:
about 13.8 core-hours for naive, 14.2 for occt. *fails* has errored on every attempt ever
recorded, so it needs an engine fix or a longer cap, and **nothing on record says what those
cost**, because none of them ever finished.

**occt has now measured all 8,235** — the 2,517 it had never attempted are done — so its gap is
entirely renders it threw away before the `--keep` fix, not parts it has yet to reach.

**The naive job did not finish: it was SIGTERMed at its deadline**, at 58%. `onto logs 0ac8d710`
ends `worst shard exit 143`. Its 1,837 *redraw* parts are the ones it never got to, and they need
a new job rather than a resumed one.

## The bug

`compare-silhouette-truth.py` renders each part to a temp dir, rasterizes it to compare against
the truth mask, and unlinks it. The `--keep DIR` flag exists to save them and neither
`census-shard.sh` nor `run-census.sh` passed it. Both now do (`ab116b5`).

## Two jobs, one engine each

| | studio | msb-uai |
|---|---|---|
| job | `62bb81bd` | `0ac8d710` |
| engine | occt | naive |
| deadline | ~23:28 | ~23:39 |
| scope | remaining ~2,519 of 8,235 (`--skip-done` skips what run 1 measured) | all 6,626 non-degenerate parts, fresh JSONLs |
| renders | only the parts it newly reaches | every part it runs |
| collected into | `out/census` | `out/census-naive` |

Both are collected by `onto fetch --stream --every 10m`, logging to `out/census-stream.log` and
`out/census-naive-stream.log`. Those are plain background processes: they die with the machine,
and re-running the same command picks up only what accumulated meanwhile.

**occt will still be missing renders for the 5,716 parts run 1 already measured.** That is the
open backfill: 2,552 parts for the flagged ones only, 11,335 for everything. Both core-hour
figures those carried (29 and 104) were pre-fix; see below for the occt half re-derived, and note
that naive gained only the two `geom2d` commits, worth **1.23x** (484.4s → 393.0s over the 14-part
bench; the shared fill half of it 1.35x, and the total is close to this box's ±13% noise floor).
It has to wait for `62bb81bd` — onto locks a tree to one job.

## Run 1 is archived, not lost

`out/census-run1/` holds every JSONL, the logs and the old shard lists — 54 files. It is the
record of what was measured; only the drawings are gone.

## Degenerate parts have their own lists — superseded, read for the reasoning only

Every count below is from before the run that followed it; `scripts/census-coverage.py` has the
live ones. What still holds is the argument: a `TimeoutError` row records the part *and* the
code's speed, so these lists are artifacts of the pre-fix code, not properties of the geometry.


`scripts/census-triage.py <archive-dir> <engine> <n>` separates parts where every recorded row
errored from the rest, writes `out/census/<engine>-degenerate.txt`, and splits the remainder into
shards. The degenerate file is a plain list, so `--list out/census/occt-degenerate.txt` re-runs
exactly the failures after a timeout bump or an engine fix.

naive: 1,609 degenerate of 8,235 — 1,596 TimeoutError, 10 ProcessDied, 3 GEOSException.
occt: 985 of the 5,716 it reached — 900 TimeoutError, 61 ProcessDied, 13 TypeError,
7 GEOSException, 3 LinAlgError, 1 RuntimeError. **That list is incomplete**: 2,517 parts were
never attempted, so `62bb81bd` will find more.

The timeout dominates both, and that makes both lists pre-fix artifacts. A `TimeoutError` row
records the part *and* the code's speed, and occt is now 3.24x faster than the code that wrote
these — so most of the 900 are a list the bug produced rather than parts occt cannot draw. Re-run
the degenerate lists post-fix before reading either as a property of the geometry. Nothing here has
been re-run at a longer `--timeout` either.

The same cut applies to `62bb81bd`, which runs the pre-fix code for its whole life: **its measured
rows stand and its failure rows do not.** The SVG is byte-identical across the three perf commits,
so accuracy is unaffected by what the render cost to produce; the timings in those rows are dead,
and every error row it contributes needs re-running with the rest.

## msb-uai, newly provisioned

It had nothing this morning. What it needed, and the traps:

- **Its agent was at the default 30m job ceiling**, so `--timeout 10h` would have been clamped
  and killed at 30m with no warning. Reinstalled with `onto install --max-job-time 12h`;
  pairing survived.
- **resvg is version-pinned and brew now serves 0.48.1.** The 0.47.0 binary came from
  `/opt/homebrew/Cellar/resvg/0.47.0/bin/resvg` on the laptop, sha `3903d990…`, which matches
  studio's byte for byte. The wrong one silently makes a node's rows incomparable.
- **`vendor/` and `.venv` are gitignored, so sync never carries them.** vendor was rsynced from
  the laptop; `parts/` and `p/` are 36,741 files on the laptop, studio and msb-uai alike. The
  ~72-file difference between the trees is all `models/` and `mklist*`, which the census never
  reads.
- **naive needs only the base deps plus scipy.** `cadquery-ocp` is occt-only, so msb-uai cannot
  run occt as it stands.
- **macOS rsync has no `--info=progress2`.** It fails with a usage dump that looks like a bad
  path.

Comparability is verified rather than assumed: msb-uai's smoke run of `3001` under naive gave
`extra_px=14590, missing_px=0, 99th 0.45, max 0.52` — identical to studio's run-1 row for it.

## Two sessions

Another session owns studio/occt and the script changes. Coordinate before dispatching to either
node: one job per tree, and a second dispatch loses the lock race rather than queueing.

## Decided, not yet started

**occt render backfill: all 4,733 measured-but-never-drawn parts**, not just the flagged ones.
Run 1 spent 47.8 core-hours on exactly these; applying the measured per-band speedup curve to
their own run-1 timings gives **16.6 core-hours**, an effective 2.87x rather than the aggregate
3.24x. The curve, from the 120-part diff sample
(`docs/census-timings/occt-diff-sample120-timings.jsonl`):

| run-1 band | n | pre-fix | HEAD | speedup |
|---|---|---|---|---|
| 0-10s | 41 | 129.8s | 30.9s | 4.20x |
| 10-30s | 59 | 741.1s | 213.4s | 3.47x |
| 30-60s | 15 | 436.6s | 135.5s | 3.22x |
| 60-120s | 5 | 294.0s | 114.2s | 2.58x |

The gain falls as parts get more expensive, which is why the backfill's mix matters: 789 of its
parts sit in the 60-120s band (18.4 core-hours pre-fix) and 189 above 120s (8.8). **The 120s+ band
is extrapolated** — the sample was capped at 120s, so it reuses the 60-120s factor and 16.6 is
optimistic by however much that understates. `out/census/occt-backfill.txt` is that list.

**It runs on onto's item dispatch, not on fixed shards.** `scripts/census-batch.sh` measures one
comma-separated batch, and `onto run --each` deals the batches out under a pool onto sizes from the
node's free cores. Batches are 25 parts because `import cadquery` costs 6.2s against a 21.6s median
part — one process per part would spend 8.1 hours starting interpreters — and they are dealt
longest-first off each part's run-1 cost, which puts every batch between 13.3 and 24.6 minutes
where id order would have produced a 50-minute item beside three-minute ones. Each batch writes its
own `<engine>-<first part>.jsonl`: `Runner` rewrites `<jsonl>.inflight` per item, so batches sharing
one JSONL would share that marker and a crash in one would bury another's part as `ProcessDied`.
The 240s watchdog is carried into that script, and `--retries 3` is what turns a killed batch back
into a finished one, since a retry redoes only what `--skip-done` has not banked.

The five-shard shape it replaces left studio at 1.4 cores of 10, and its tail ran one shard alone
for the last hour — with balancing 25x coarser than the batches, the aggregate rate stopped
predicting the finish as soon as that happened.

**Timeouts: probe 100 before committing.** `out/census/{occt,naive}-probe100.txt` are evenly
spaced samples of the degenerate sets. What the probe is for has changed: at 3.24x it is no longer
"what does a 600s cap buy" but "how many of these still fail at 120s now" — most of the occt list
should simply pass, and the answer decides whether a longer cap is wanted at all.

**The degenerate re-run cannot be costed from run 1 at all.** Those 985 parts burned 30.6
core-hours without one of them completing, so nothing on record says how long they take — only
that they exceed 120s under the old code. The probe is the only way to get a number, which is
what makes it worth running before the re-run rather than after.

Both wait on studio's tree, which `62bb81bd` holds. It frees when the last shard exits, not at the
deadline: at 95% on 2026-09-05, and 5.6 parts/min sustained over the preceding 86 minutes, that is
**any time from about 21:00**, up to two and a half hours early. Treat it as a floor rather than an
estimate — being ready early costs nothing and being late leaves the tree idle. The tail is the
slow parts and one of the five shards has already finished, so both push the other way.

## What run 1's timings say

11,359 parts produced a measurement. naive median 13.3s, p90 84.7s, max 1038s; occt median 21.6s,
p90 90.3s, max 678s. The distribution is broad — no bin holds more than 8% — and there is no gap
between 60s and 120s: 1,605 successful parts land in that band.

A hard cap would have cut, of successful parts: 30s → 34.9%, 60s → 18.2%, 90s → 9.4%,
120s → 4.1%, 180s → 0.9%, 300s → 0.2%. So 120s is a defensible number.

**But the guard does not enforce it.** `batch.py` arms `signal.setitimer` around the work
function, and the handler runs only between Python bytecodes — so a part inside one long OCCT,
GEOS or numpy call runs straight past the deadline and finishes. That is how 464 successful rows
exceed 120s, the largest at 1038s. The cap therefore selects on *where* time is spent rather than
how much, and two equally slow parts get opposite treatment.

**It cost a machine on 2026-09-05.** `occt r2` under `62bb81bd` sat inside one OCCT call for 2h58m
and reached a 185.9 GB physical footprint — `ps` showed 3.4 GB because the rest was paged out —
taking studio's swap to 40 GB and its boot disk to within about 45 minutes of full. Killing the
worker was the whole fix: the shard restarted, buried the part as `ProcessDied` off the `.inflight`
marker, and stepped over it.

So enforcement has to come from outside the process, and `Runner` already writes what it needs.
`census-shard.sh` now compares `<jsonl>.inflight`'s mtime against `HARD` (240s), kills the worker,
and lets the restart loop bury the part as `ProcessDied` and step over it (`2f2f574`). **The
ceiling is a crash guard, not a second cap** — every part it kills is one the 120s cap already
meant to kill and structurally could not.

**It runs as a ratchet, starting at 240s** (`fa2cfd6`). Each pass runs a list, triages against that
same list, and writes what is still undone as the next pass's list at a higher ceiling:

    HARD=240 scripts/census-shard.sh occt h240 120
    scripts/census-triage.py out/census occt \
        --corpus out/census/occt-h240.txt --out out/census/occt-h480.txt
    HARD=480 scripts/census-shard.sh occt h480 120

The tag names the list file, so the first pass's input is whatever list you are starting from,
saved as `out/census/occt-h240.txt`. Stop when the count stops falling: what is left then is parts
the engine cannot draw rather than parts it was not given long enough to draw. Nothing is discarded,
which is why a single ceiling was rejected — it forces a choice between catching hangs early and
throwing away parts that were merely slow. 240s also keeps any one part from burning an hour of a
shard, which a 3600s guard would have allowed.

**The next pass's list is every part with no successful row**, not the degenerate test `p in bad
and p not in good`. A pass killed at its own deadline leaves parts it never reached, and those are
in neither set — against `occt-r3.txt` that is 125 of 363, which the degenerate test would have
dropped from every later pass without printing anything. The error breakdown counts those as
`(never attempted)` separately, and that distinction is the signal to read: never-attempted means
the job ran out of time and wants requeueing, `TimeoutError` means the ceiling is too low and wants
raising. The count alone cannot tell them apart.

## Where the time actually goes

`compare-silhouette-truth.py` now records a `phase` map on every row — `render`, `rasterize`,
`truth_mask`, `compare` — so this answers itself from run 2 onward. Run 1 had only a total, so the
numbers below come from re-measuring 32 naive parts sampled across its duration range
(`scripts/census-phase-probe.py`, data in `docs/census-timings/phases.jsonl`).

**The renderer is 96.1% of it.** truth_mask 3.0%, compare 0.6%, rasterize 0.3%. The share moves
with part size: a part under 2s is mostly fixed overhead, by 10s render is ~90%, past 30s it is
96-98%. So making the census cheaper means the hidden-line pass and nothing else — `truth_mask`'s
pure-Python scanline fill looks alarming and costs 3%.

## Half of occt's render was a Python idiom

`analytic_creases` and `_group_planes` walked every edge of the sewn shape as
`list(amap.FindFromIndex(i))`. Exhausting a pybind11 iterator over an OCP collection raises
`StopIteration` from a thrown C++ exception, and unwinding it through OCP's library costs ~3ms per
call however few shapes the collection holds — 478 edges on 3941 cost 1.76s in each function. Fixed
in c770700 with `Size()`/`First()`/`Last()`; SVG is byte-identical on eight specimens.

`scripts/census-engine-bench.py` splits the render phase into the hidden-line call and the shading,
fill and SVG emit that follow it, over 14 occt parts sampled across run 1's duration bands. Data in
`docs/census-timings/occt-render-{d487865,c770700}.jsonl`:

| | before (d487865) | after (c770700) |
|---|---|---|
| render | 291.4s | 137.6s |
| geometry | 193.0s (66%) | 42.8s (31%) |
| the rest | 98.4s | 94.8s |

**3.24x on the census's own workload** — 1601.5s → 493.9s over a seeded 120-part draw from run 1's
occt rows (100 under 30s, 20 between 30 and 120s), byte-identical on every one. The 14-part figure
from the table above is 2.12x because that sample is weighted toward the slow tail, where the gain
is smallest; the fix scales with edge count, so cheap parts gain most (6521: 1.78s → 0.15s). Note
"the rest" holding still across the two revisions — that is the instrumentation checking itself.

`scripts/census-render-diff.sh d487865 docs/census-timings/occt-diff-sample120.txt` re-runs that
byte diff at any later revision.

**The rest of the render is `fill_ops`, and it is shared by every engine.** Geometry is now 31% of
a render and 10-14% on the baseplates 0901/0902, the slowest parts sampled. `fill_ops` holds the
remainder — 23.6s of 0901's 28.8s, most of it in `clip_pass`. Not `order_faces`: its pair test is
O(n^2) but 98.1% of 0901's 103,740 pairs bail on the bbox check, for 1.2s all told.

Two costs came out of it (c4834f0, 2fcde17), both byte-identical across 36 parts:

- `geom2d._assign_edges` offered every ring to every candidate ellipse, then walked the ring's
  vertices in Python. Prefiltering candidates by bbox and vectorizing the sweep took 0901 from
  526,955 `_vertex_angles` calls and 9.31s to 8,419 calls and 0.79s.
- Every `Polygon()` empty sentinel in `geom2d` parsed the WKT text `"POLYGON EMPTY"` at 2us a
  call. Part-dependent: 2.1M calls on 44937, 872 on 0902.

0901 end to end: 28.8s → 21.0s under the profiler. What remains is GEOS itself — union,
intersection, difference and `union_all` — which is real geometric work, not overhead.

**Job `62bb81bd` predates the fix**, so every row it writes carries the old cost. At its sustained
5.3 parts/min it reached 89% of 8,235 with five hours still on its ~23:28 deadline, so it finishes
its shards well inside it. Restarting was not done — it would discard the in-flight shards, and the
2.12x is a 14-part estimate from the laptop rather than from studio.

## The census runs the most expensive mode of the four

`scripts/census-mode-sweep.py` timed 10 parts through every mode that can emit SVG, same parts each
time (`docs/census-timings/modes.jsonl`):

| mode | render | rasterize | svg |
|---|---|---|---|
| cel+none | 0.62s | 3.11s | 15K |
| cel+flat3 | 0.65s | 2.96s | 15K |
| outline+none | 5.15s | 0.16s | 26K |
| **outline+flat3** (the census) | **11.09s** | 0.12s | 61K |

`cel` renders 17x faster than what the census runs, and dropping `flat3` alone halves it. This is a
cost measurement only — nothing here says cel is substitutable for measuring silhouette accuracy,
and cel rasterizes to a ~209 megapixel image at zoom 8, past PIL's default bomb guard.

**`normal` shading cannot be measured this way**: the CLI refuses to write SVG for it ("--shading
must be outline or cel"), so the mode grid is 2x2, not 3x2.

## Expected output volume

naive writes exactly two files per part, `<part>.svg` and `<part>.fit.json`, at ~50 KiB per part
measured over the first 820 it finished. The full 6,626-part run projects to **13,252 files,
~324 MiB**.

`onto fetch --stream` could report this without any protocol change: it already fetches a manifest
each round and the job already prints `onto: progress <done>/<total>`. Multiplying one by the other
projects the finished size. Not built.

## naive will not finish inside its deadline

It sustains ~8.0 parts/min, so 6,626 parts need ~14h against a 10h deadline — it will reach roughly
73% and be killed. **Deliberately left alone:** these are incremental jobs, the shards resume from
their JSONL, and whatever is left is requeued as another job. The calculus would be different for a
job with one indivisible deliverable, which is recorded as an open question in onto's
`2026-09-04-2.0-open-decisions.md`.
