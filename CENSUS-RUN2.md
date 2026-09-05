# Census run 2 — what is running and where

**What this is:** the state of the silhouette census as of 2026-09-05 13:45, across two nodes.
**Who it's for:** whoever picks this up next, in this repo. Assumes `HANDOFF.md` for what the
census measures; this file only carries what changed today.

**The question it answers:** run 1 measured 13,928 parts and saved no drawings. What replaced it?

## The bug

`compare-silhouette-truth.py` renders each part to a temp dir, rasterizes it to compare against
the truth mask, and unlinks it. The `--keep DIR` flag exists to save them and neither
`census-shard.sh` nor `run-census.sh` passed it. Both now do (uncommitted, from another session).

## Two jobs, one engine each

| | studio | msb-uai |
|---|---|---|
| job | `62bb81bd` | `0ac8d710` |
| engine | occt | naive |
| deadline | ~18:40 | 23:40 |
| scope | remaining ~2,519 of 8,235 (`--skip-done` skips what run 1 measured) | all 6,626 non-degenerate parts, fresh JSONLs |
| renders | only the parts it newly reaches | every part it runs |
| collected into | `out/census` | `out/census-naive` |

Both are collected by `onto fetch --stream --every 10m`, logging to `out/census-stream.log` and
`out/census-naive-stream.log`. Those are plain background processes: they die with the machine,
and re-running the same command picks up only what accumulated meanwhile.

**occt will still be missing renders for the 5,716 parts run 1 already measured.** That is the
open backfill: 2,552 parts / 29 core-hours for the flagged ones only, 11,335 / 104 for
everything. It has to wait for `62bb81bd` — onto locks a tree to one job.

## Run 1 is archived, not lost

`out/census-run1/` holds every JSONL, the logs and the old shard lists — 54 files. It is the
record of what was measured; only the drawings are gone.

## Degenerate parts have their own lists

`scripts/census-triage.py <archive-dir> <engine> <n>` separates parts where every recorded row
errored from the rest, writes `out/census/<engine>-degenerate.txt`, and splits the remainder into
shards. The degenerate file is a plain list, so `--list out/census/occt-degenerate.txt` re-runs
exactly the failures after a timeout bump or an engine fix.

naive: 1,609 degenerate of 8,235 — 1,596 TimeoutError, 10 ProcessDied, 3 GEOSException.
occt: 985 of the 5,716 it reached — 900 TimeoutError, 61 ProcessDied, 13 TypeError,
7 GEOSException, 3 LinAlgError, 1 RuntimeError. **That list is incomplete**: 2,517 parts were
never attempted, so `62bb81bd` will find more.

The timeout dominates both. Nothing here has been re-run at a longer `--timeout`.

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

**occt render backfill: all 4,733 measured-but-never-drawn parts** (~48 core-hours), not just the
flagged ones. `out/census/occt-backfill.txt` is that list. Needs a fresh JSONL so `--skip-done`
skips nothing, the same shape as the naive run on msb-uai.

**Timeouts: probe 100 before committing.** `out/census/{occt,naive}-probe100.txt` are evenly
spaced samples of the degenerate sets, to learn what a 600s cap actually buys before spending
dozens of core-hours on 2,523 parts.

Both wait on studio's tree, which `62bb81bd` holds.

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
how much, and two equally slow parts get opposite treatment. Worth fixing independently of what
number is chosen.

**Per-phase timings do not exist.** Every row carries one `secs`, measured across the whole of
`compare-silhouette-truth.py`. Splitting it into geometry / rasterize / truth-mask / compare needs
the script instrumented; nothing recorded so far can be re-analysed to get it.
