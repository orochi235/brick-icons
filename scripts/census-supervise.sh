#!/bin/sh
# Run the census shards and restart any that die, until each one is done.
#
#     scripts/census-supervise.sh [shards_per_engine] [per_part_timeout_s]
#
# occt segfaults inside OCCT on some parts and takes its shard down with it. A
# shard that dies stays dead, so an unattended night loses that engine one
# shard at a time. Restarting is safe and makes progress: the shard resumes
# from its JSONL with --skip-done, and the part named in <jsonl>.inflight is
# recorded as ProcessDied on the way back in, so the killer is stepped over
# rather than hit again.
set -eu
cd "$(dirname "$0")/.."
SHARDS=${1:-4}
TIMEOUT=${2:-120}
DIR=out/census
MAX_RESTARTS=${MAX_RESTARTS:-300}

[ -f "$DIR/order.txt" ] || { echo "run scripts/run-census.sh first: no $DIR/order.txt" >&2; exit 1; }
for i in $(seq 0 $((SHARDS - 1))); do
  [ -f "$DIR/shard-$i.txt" ] || awk -v n="$SHARDS" -v i="$i" 'NR % n == i' "$DIR/order.txt" > "$DIR/shard-$i.txt"
done

for engine in naive occt; do
  for i in $(seq 0 $((SHARDS - 1))); do
    (
      n=0
      while [ "$n" -le "$MAX_RESTARTS" ]; do
        .venv/bin/python scripts/compare-silhouette-truth.py \
          --list "$DIR/shard-$i.txt" --engine "$engine" --timeout "$TIMEOUT" \
          --jsonl "$DIR/$engine-s$i.jsonl" --skip-done \
          >> "$DIR/logs/$engine-s$i.log" 2>&1 && break
        n=$((n + 1))
        echo "--- $engine shard $i died (restart $n) at $(date '+%H:%M:%S') ---" >> "$DIR/logs/$engine-s$i.log"
        sleep 2
      done
      echo "--- $engine shard $i finished at $(date '+%H:%M:%S') after $n restart(s) ---" >> "$DIR/logs/$engine-s$i.log"
    ) &
    echo "supervising $engine shard $i (pid $!)"
  done
done
