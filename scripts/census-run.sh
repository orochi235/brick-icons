#!/bin/sh
# Run the whole census: every shard census-reshard.py laid out, in parallel,
# under one process. onto locks a working tree to one job, which is the right
# shape here — the census is one workload on one tree — so this is what an onto
# job runs:
#
#     onto run --detach --timeout 10h --in brick-icons --env PATH=... <node> \
#       -- <tree>/scripts/census-run.sh 120
#
# A progress line joins the shards' own output every 5 minutes, so `onto logs
# -f` answers "is it still moving" without reading eight interleaved streams.
set -eu
cd "$(dirname "$0")/.."
TIMEOUT=${1:-120}
HEARTBEAT=${2:-300}
DIR=out/census

scripts/census-heartbeat.sh "$HEARTBEAT" &
heart=$!
# Killing the heartbeat is the last thing this script does, including when the
# job is cancelled — otherwise it outlives the job onto thinks it supervises.
trap 'kill "$heart" 2>/dev/null || true' EXIT INT TERM

pids=""
for f in "$DIR"/naive-r*.txt "$DIR"/occt-r*.txt; do
  [ -f "$f" ] || continue
  b=$(basename "$f" .txt)
  scripts/census-shard.sh "${b%%-*}" "${b#*-}" "$TIMEOUT" &
  pids="$pids $!"
  echo "started ${b%%-*} ${b#*-} (pid $!)"
done
[ -n "$pids" ] || { echo "no shard lists in $DIR; run scripts/census-reshard.py first" >&2; exit 1; }

rc=0
for p in $pids; do wait "$p" || rc=$?; done
echo "--- census run finished, worst shard exit $rc ---"
exit "$rc"
