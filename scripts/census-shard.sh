#!/bin/sh
# Run one census shard in the foreground until it is done, restarting it if it
# dies. Output goes to stdout/stderr, so the onto job that launched it owns the
# log and `onto logs -f` follows it.
#
#     scripts/census-shard.sh <engine> <tag> [per_part_timeout_s]
#
# Reads out/census/<engine>-<tag>.txt, appends to out/census/<engine>-<tag>.jsonl,
# and keeps every render under out/census/renders/<engine>/ (KEEP= to move it).
# Without --keep the census measures a drawing and then deletes it, so a row
# that flags a part cannot be looked at without paying the render again.
# scripts/census-reshard.py writes those list files. Launch one job per shard:
#
#     onto run --detach --timeout 10h --in brick-icons --env PATH=... <node> \
#       -- <tree>/scripts/census-shard.sh occt r0 120
#
# occt segfaults inside OCCT on some parts and takes the shard down with it.
# Restarting is safe and makes progress: the shard resumes from its JSONL with
# --skip-done, and the part named in <jsonl>.inflight comes back as ProcessDied,
# so the killer is stepped over rather than hit again.
#
# HARD (default 240s) is a watchdog, not the measurement cap. --timeout arms
# signal.setitimer, whose handler only runs between bytecodes, so a part inside
# one long OCCT call runs past it forever -- one reached a 185.9 GB footprint
# over 2h58m and nearly filled a boot disk. Killing the worker from outside is
# the whole fix; the restart loop above does the rest. Parts it kills are not
# lost: they land in the JSONL as ProcessDied, census-triage.py collects them,
# and the list is re-run at a higher HARD until the set stops shrinking.
set -eu
cd "$(dirname "$0")/.."
engine=${1:?engine}
tag=${2:?shard tag}
TIMEOUT=${3:-120}
DIR=out/census
KEEP=${KEEP:-out/census/renders}
MAX_RESTARTS=${MAX_RESTARTS:-300}
HARD=${HARD:-240}

# The shard's own "7/1437 <part> ..." lines are echoed through unchanged and
# each one also becomes an `onto: progress` line, so `onto top` draws a bar per
# shard. onto sees one job here -- it locks a tree to a single job -- and this
# is what breaks that job back down into the eight things it is really doing.
rcfile=$(mktemp)
trap 'rm -f "$rcfile"' EXIT

# Runner rewrites <jsonl>.inflight at the start of every item, so its mtime is
# the current part's start time -- the one clock a watchdog can read from
# outside the process.
inflight="$DIR/$engine-$tag.jsonl.inflight"
watchdog() {
  while sleep 15; do
    pid=$(pgrep -f "compare-silhouette-truth.py --list $DIR/$engine-$tag.txt") || continue
    [ -f "$inflight" ] || continue
    age=$(( $(date +%s) - $(stat -f %m "$inflight") ))
    [ "$age" -lt "$HARD" ] && continue
    echo "--- $engine $tag: $(cat "$inflight") stuck ${age}s > ${HARD}s, killing $pid ---" >&2
    kill -9 "$pid" 2>/dev/null || true
  done
}
watchdog &
wdpid=$!
trap 'rm -f "$rcfile"; kill "$wdpid" 2>/dev/null || true' EXIT

n=0
while [ "$n" -le "$MAX_RESTARTS" ]; do
  {
    .venv/bin/python scripts/compare-silhouette-truth.py \
      --list "$DIR/$engine-$tag.txt" --engine "$engine" --timeout "$TIMEOUT" \
      --jsonl "$DIR/$engine-$tag.jsonl" --skip-done --keep "$KEEP"
    echo $? > "$rcfile"
  } | awk -v label="$engine $tag" '
      # plan first: its raw line is machine-directed, and echoing it unlabelled
      # would hand onto a plan for a unit with no name
      /^onto: plan / { printf "onto: plan %s %s\n", $3, label; next }
      { print }
      /^[0-9]+\/[0-9]+ / { split($1, a, "/"); printf "onto: progress %s/%s %s\n", a[1], a[2], label }
      { fflush() }'
  [ "$(cat "$rcfile")" = "0" ] && break
  n=$((n + 1))
  echo "--- $engine $tag died, restart $n at $(date '+%H:%M:%S') ---" >&2
  sleep 2
done
echo "--- $engine $tag done after $n restart(s) ---" >&2
