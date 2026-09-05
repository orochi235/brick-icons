#!/bin/sh
# Fill renders/<source>/<part>.svg over the census corpus, sharded.
#
#     scripts/run-render-store.sh [shards] [per_part_timeout_s] [sources]
#
# Detached by design: a foreground call dies at the tool timeout no matter what
# the process is doing. Each shard streams JSONL and resumes on its own, so
# re-running this picks up where the night stopped.
#
# Naive first: occt segfaults on some parts and is the slower engine, and one
# source finished beats two half-done.
set -eu
cd "$(dirname "$0")/.."
SHARDS=${1:-8}
TIMEOUT=${2:-180}
SOURCES=${3:-naive}
DIR=out/store
mkdir -p "$DIR/logs"

[ -f out/census/parts.txt ] || { echo "need out/census/parts.txt"; exit 1; }
[ -f "$DIR/order.txt" ] || sort -R out/census/parts.txt > "$DIR/order.txt"
TOTAL=$(wc -l < "$DIR/order.txt" | tr -d ' ')

for i in $(seq 0 $((SHARDS - 1))); do
  awk -v n="$SHARDS" -v i="$i" 'NR % n == i' "$DIR/order.txt" > "$DIR/shard-$i.txt"
done

for i in $(seq 0 $((SHARDS - 1))); do
  nohup .venv/bin/python scripts/build-render-store.py \
    --list "$DIR/shard-$i.txt" --sources "$SOURCES" --timeout "$TIMEOUT" \
    --log "$DIR/s$i.jsonl" > "$DIR/logs/s$i.log" 2>&1 &
  echo "started shard $i (pid $!)"
done

{
  echo "# Render store run $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "- commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
  echo "- corpus: $TOTAL parts, shuffled into $SHARDS shards"
  echo "- sources: $SOURCES, per-part cap: ${TIMEOUT}s"
  echo
  echo "Progress: scripts/render-store-report.sh"
} >> "$DIR/RUN.md"
echo "--- watch with: scripts/render-store-report.sh"
