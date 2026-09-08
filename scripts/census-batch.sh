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
# now renders each part in a forked child and kills its process group, so a
# part inside one long OCCT call is stopped where signal.setitimer alone never
# reached it -- one had a 185.9 GB footprint over 2h58m and nearly filled
# studio's boot disk. HARD is what is left for the pass itself wedging, and
# for renders orphaned by a kill from outside this script. Parts it kills are
# not lost: this script buries the one named in .inflight as ProcessDied
# before it exits, and a re-run steps over it.
set -eu
cd "$(dirname "$0")/.."
engine=${1:?engine}
timeout=${2:?per-part timeout}
dir=${3:?directory to write this run of JSONLs into}
batch=${4:?comma-separated part ids}
KEEP=${KEEP:-out/census/renders}
HARD=${HARD:-240}
POLL=${POLL:-15}
# Resident GB one render may reach. A healthy part on this corpus peaks under
# 1 GB; the parts that wedge a node pass 4 GB inside a minute and keep going,
# so this separates them without touching anything that works.
MEM_GB=${MEM_GB:-4}
EXTRA=${EXTRA:-}
# The slot this tree's drawings and rows belong to, for the slots whose names
# carry no facet word -- `out/census-occt` derives to silhouette-occt and
# always will. Stated here, the label rides home with the tree. Written via mv
# because every worker on the job runs this line against the same directory.
SOURCE=${SOURCE:-}

mkdir -p "$dir"
if [ -n "$SOURCE" ] && [ ! -f "$dir/SOURCE" ]; then
  tmp_src="$dir/.SOURCE.$$"
  printf '%s\n' "$SOURCE" > "$tmp_src" && mv -f "$tmp_src" "$dir/SOURCE"
fi
first=${batch%%,*}
jsonl="$dir/$engine-$first.jsonl"
inflight="$jsonl.inflight"

IFS=,
# shellcheck disable=SC2086
set -- $batch
unset IFS
PASSES=${PASSES:-$#}

# onto reads these off this item's own stdout pipe, so an unlabelled line is
# attributed to this worker instead of colliding with the other ten on the
# job's shared log. Without them the only progress onto sees is the batch
# finishing, which for 25 parts is a bar that moves once every twenty minutes.
rc=$(mktemp)
worker=
trap 'rm -f "$rc"; kill "$worker" 2>/dev/null || true' EXIT INT TERM

# One pass per part at most. A segfault kills the interpreter partway through
# the batch, so a single pass leaves every part after the killer unattempted
# and unrecorded -- absent from the census rather than failed in it, and so
# invisible to the coverage list the next run is built from. Each pass resumes
# from the JSONL and buries the part that died, so a pass only steps forward.
attempt=0
code=
while :; do
  {
    # EXTRA carries the facet's render config (--shade-style, --line-width,
    # --silhouette-width). Deliberately word-split: it is a flag string, and
    # onto passes it through --env as one variable.
    # shellcheck disable=SC2086
    .venv/bin/python scripts/compare-silhouette-truth.py "$@" \
      --engine "$engine" --timeout "$timeout" --mem-gb "$MEM_GB" \
      --jsonl "$jsonl" --skip-done --keep "$KEEP" ${EXTRA:-}
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

  # .inflight's mtime is the current part's start time, and the only clock a
  # watchdog can read from outside the process.
  # onto can stop this job mid-part so a test run gets a quiet machine, and
  # while it is stopped the wall clock keeps going but this part does not. Left
  # uncorrected, every part in flight is instantly older than HARD the moment
  # the job resumes and the watchdog kills all of them — losing exactly the work
  # the pause existed to keep. $ONTO_PAUSED holds the job's cumulative stopped
  # seconds; what matters is how much of it accrued since this part started.
  paused_now() {
    if [ -n "${ONTO_PAUSED:-}" ] && [ -r "${ONTO_PAUSED:-}" ]; then
      cat "$ONTO_PAUSED" 2>/dev/null || echo 0
    else
      echo 0
    fi
  }
  # Every process this batch's renders run in. The pipeline's pid is grep's, so
  # they are found by the jsonl path they were handed, which is unique to this
  # batch. There is always more than one: the pass's python, the child it forks
  # per part, and the grandchild occt._unify_survives forks inside that.
  batch_pids() {
    pgrep -f "compare-silhouette-truth.py .* --jsonl $jsonl " 2>/dev/null || true
  }

  last_start=
  paused_at=0
  idle_at=
  while kill -0 "$worker" 2>/dev/null; do
    sleep "$POLL"
    now=$(date +%s)
    if [ -f "$inflight" ]; then
      idle_at=
      started=$(stat -f %m "$inflight")
      # A new part: note what the job had already spent stopped, so only time
      # lost during *this* part is subtracted.
      if [ "$started" != "$last_start" ]; then
        last_start=$started
        paused_at=$(paused_now)
      fi
      age=$(( now - started - ($(paused_now) - paused_at) ))
      stuck=$(cat "$inflight" 2>/dev/null || echo "?")
    else
      # No part is claimed and renders for this batch are still alive: they were
      # orphaned, and nothing will ever write their row or reap them. Skipping
      # the check here — which is what `[ -f "$inflight" ] || continue` did — is
      # how a node ends up carrying renders no watchdog is looking at. Between
      # parts the same state lasts a second or two, so it gets the same grace as
      # a stuck part rather than an instant kill.
      if [ -z "$(batch_pids)" ]; then
        idle_at=
        continue
      fi
      [ -n "$idle_at" ] || idle_at=$now
      age=$(( now - idle_at ))
      stuck="an orphan; no part claimed"
    fi
    [ "$age" -lt "$HARD" ] && continue
    py=$(batch_pids)
    if [ -z "$py" ]; then
      # Never fall back to $worker. That is grep, and killing it returns 137
      # while the runaway keeps growing — the watchdog causing the failure it
      # exists to prevent, and onto would start another worker beside it.
      echo "--- $first batch: $stuck stuck ${age}s but no worker matched; NOT killing ---" >&2
      continue
    fi
    echo "--- $first batch: $stuck stuck ${age}s > ${HARD}s, killing $py ---" >&2
    # Unquoted, and this is the whole reason the watchdog had never once killed
    # anything: pgrep returns one pid per line, and "$py" handed kill every pid
    # as a single argument, which it rejects outright ("arguments must be
    # process or job IDs") into the `|| true`.
    # shellcheck disable=SC2086
    kill -9 $py 2>/dev/null || true
    break
  done

  wait "$worker" 2>/dev/null || true
  worker=
  # Empty as well as missing: a killed worker never writes the file, and
  # `exit ""` is 255, which would hide the signal that did it.
  code=$(cat "$rc" 2>/dev/null || true)
  [ -n "$code" ] || code=137
  : > "$rc"

  # The part that died is named in .inflight and has no row anywhere. Bury it
  # before the next pass, which is also what stops that pass hitting it again.
  if [ -s "$inflight" ]; then
    # shellcheck disable=SC2086
    .venv/bin/python scripts/compare-silhouette-truth.py --bury \
      --engine "$engine" --jsonl "$jsonl" ${EXTRA:-} || true
  fi

  if [ "$code" = "0" ]; then
    break
  fi
  # onto prune: stop at a part boundary rather than starting another pass.
  if [ -n "${ONTO_PRUNE:-}" ] && [ -f "$ONTO_PRUNE" ]; then
    echo "--- $first batch pruned after pass $attempt ---" >&2
    break
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$PASSES" ]; then
    break
  fi
  echo "--- $first batch: pass $attempt ended rc=$code, resuming ---" >&2
done

rm -f "$rc"
trap - EXIT INT TERM
exit "$code"
