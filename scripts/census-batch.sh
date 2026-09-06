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
POLL=${POLL:-15}
EXTRA=${EXTRA:-}

mkdir -p "$dir"
first=${batch%%,*}
jsonl="$dir/$engine-$first.jsonl"
inflight="$jsonl.inflight"

IFS=,
# shellcheck disable=SC2086
set -- $batch
unset IFS

# onto reads these off this item's own stdout pipe, so an unlabelled line is
# attributed to this worker instead of colliding with the other ten on the
# job's shared log. Without them the only progress onto sees is the batch
# finishing, which for 25 parts is a bar that moves once every twenty minutes.
rc=$(mktemp)
{
  # EXTRA carries the facet's render config (--shade-style, --line-width,
  # --silhouette-width). Deliberately word-split: it is a flag string, and
  # onto passes it through --env as one variable.
  # shellcheck disable=SC2086
  .venv/bin/python scripts/compare-silhouette-truth.py "$@" \
    --engine "$engine" --timeout "$timeout" --jsonl "$jsonl" --skip-done \
    --keep "$KEEP" ${EXTRA:-}
  echo $? > "$rc"
} | awk '
    /^onto: plan / { print; fflush(); next }
    { print }
    /^[0-9]+\/[0-9]+ / {
      split($1, a, "/")
      if ($0 ~ / FAILED /) bad++
      printf "onto: progress %s/%s\n", a[1], a[2]
      if (bad) printf "onto: failed %d/%s\n", bad, a[2]
    }
    { fflush() }' &
worker=$!
trap 'rm -f "$rc"; kill "$worker" 2>/dev/null || true' EXIT INT TERM

# .inflight's mtime is the current part's start time, and the only clock a
# watchdog can read from outside the process.
while kill -0 "$worker" 2>/dev/null; do
  sleep "$POLL"
  [ -f "$inflight" ] || continue
  age=$(( $(date +%s) - $(stat -f %m "$inflight") ))
  [ "$age" -lt "$HARD" ] && continue
  # The pipeline's pid is grep's, so the python is found by the jsonl path it
  # was handed, which is unique to this batch.
  py=$(pgrep -f "compare-silhouette-truth.py .* --jsonl $jsonl " || true)
  if [ -z "$py" ]; then
    # Never fall back to $worker. That is grep, and killing it returns 137
    # while the runaway keeps growing — the watchdog causing the failure it
    # exists to prevent, and onto would start another worker beside it.
    echo "--- $first batch: $(cat "$inflight") stuck ${age}s but no worker matched; NOT killing ---" >&2
    continue
  fi
  echo "--- $first batch: $(cat "$inflight") stuck ${age}s > ${HARD}s, killing $py ---" >&2
  kill -9 "$py" 2>/dev/null || true
  break
done

wait "$worker" 2>/dev/null || true
# Empty as well as missing: a killed worker never writes the file, and
# `exit ""` is 255, which would hide the signal that did it.
code=$(cat "$rc" 2>/dev/null || true)
[ -n "$code" ] || code=137
rm -f "$rc"
trap - EXIT INT TERM
exit "$code"
