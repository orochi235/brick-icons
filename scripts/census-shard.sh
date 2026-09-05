#!/bin/sh
# Run one census shard in the foreground until it is done, restarting it if it
# dies. Output goes to stdout/stderr, so the onto job that launched it owns the
# log and `onto logs -f` follows it.
#
#     scripts/census-shard.sh <engine> <tag> [per_part_timeout_s]
#
# Reads out/census/<engine>-<tag>.txt and appends to out/census/<engine>-<tag>.jsonl.
# scripts/census-reshard.py writes those list files. Launch one job per shard:
#
#     onto run --detach --timeout 10h --in brick-icons --env PATH=... <node> \
#       -- <tree>/scripts/census-shard.sh occt r0 120
#
# occt segfaults inside OCCT on some parts and takes the shard down with it.
# Restarting is safe and makes progress: the shard resumes from its JSONL with
# --skip-done, and the part named in <jsonl>.inflight comes back as ProcessDied,
# so the killer is stepped over rather than hit again.
set -eu
cd "$(dirname "$0")/.."
engine=${1:?engine}
tag=${2:?shard tag}
TIMEOUT=${3:-120}
DIR=out/census
MAX_RESTARTS=${MAX_RESTARTS:-300}

# The shard's own "7/1437 <part> ..." lines are echoed through unchanged and
# each one also becomes an `onto: progress` line, so `onto top` draws a bar per
# shard. onto sees one job here -- it locks a tree to a single job -- and this
# is what breaks that job back down into the eight things it is really doing.
rcfile=$(mktemp)
trap 'rm -f "$rcfile"' EXIT

n=0
while [ "$n" -le "$MAX_RESTARTS" ]; do
  {
    .venv/bin/python scripts/compare-silhouette-truth.py \
      --list "$DIR/$engine-$tag.txt" --engine "$engine" --timeout "$TIMEOUT" \
      --jsonl "$DIR/$engine-$tag.jsonl" --skip-done
    echo $? > "$rcfile"
  } | awk -v label="$engine $tag" '
      { print }
      /^[0-9]+\/[0-9]+ / { split($1, a, "/"); printf "onto: progress %s/%s %s\n", a[1], a[2], label }
      { fflush() }'
  [ "$(cat "$rcfile")" = "0" ] && break
  n=$((n + 1))
  echo "--- $engine $tag died, restart $n at $(date '+%H:%M:%S') ---" >&2
  sleep 2
done
echo "--- $engine $tag done after $n restart(s) ---" >&2
