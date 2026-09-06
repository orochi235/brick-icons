#!/bin/sh
# Measure one batch of parts in one process. Called once per line of a batch
# list by onto's item dispatch:
#
#     onto run --detach --in brick-icons --each out/census/<list>.txt \
#       <node> -- scripts/census-batch.sh occt 120 out/census/backfill {}
#
# A batch rather than a part because `import cadquery` costs 6.2s against a
# 21.6s median part: one process per part would spend 8.1 hours starting
# interpreters over the 4,733-part backfill.
#
# Each batch gets its own JSONL under <dir>, named for its first part. Runner
# writes <jsonl>.inflight beside it and rewrites it per item, so batches
# sharing one JSONL would share that marker — a crash in one would record a
# part from another as ProcessDied, and their appends would interleave.
#
# HARD (default 240s) is a watchdog, not a second measurement cap. --timeout
# arms signal.setitimer, whose handler runs only between bytecodes, so a part
# inside one long OCCT call runs past it forever: one reached a 185.9 GB
# footprint over 2h58m and nearly filled studio's boot disk. A pool sized from
# free cores can have several workers inside such a part at once, so this
# matters more here than it did for five fixed shards. Parts it kills are not
# lost — re-running the batch makes Runner bury the one named in .inflight as
# ProcessDied and step over it, which is what onto's --retries is for.
set -eu
cd "$(dirname "$0")/.."
engine=${1:?engine}
timeout=${2:?per-part timeout}
dir=${3:?directory to write this run of JSONLs into}
batch=${4:?comma-separated part ids}
KEEP=${KEEP:-out/census/renders}
HARD=${HARD:-240}

mkdir -p "$dir"
first=${batch%%,*}
jsonl="$dir/$engine-$first.jsonl"
inflight="$jsonl.inflight"

IFS=,
# shellcheck disable=SC2086
set -- $batch
unset IFS

.venv/bin/python scripts/compare-silhouette-truth.py "$@" \
  --engine "$engine" --timeout "$timeout" --jsonl "$jsonl" --skip-done --keep "$KEEP" &
worker=$!
trap 'kill "$worker" 2>/dev/null || true' EXIT INT TERM

# .inflight's mtime is the current part's start time, and the only clock a
# watchdog can read from outside the process.
while kill -0 "$worker" 2>/dev/null; do
  sleep 15
  [ -f "$inflight" ] || continue
  age=$(( $(date +%s) - $(stat -f %m "$inflight") ))
  [ "$age" -lt "$HARD" ] && continue
  echo "--- $first batch: $(cat "$inflight") stuck ${age}s > ${HARD}s, killing $worker ---" >&2
  kill -9 "$worker" 2>/dev/null || true
  break
done

trap - EXIT INT TERM
wait "$worker"
