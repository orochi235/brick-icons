#!/bin/sh
# Fill renders/<source>/<part>.svg over the census corpus, sharded.
#
#     scripts/run-render-store.sh [shards] [per_part_timeout_s] [sources]
#
# ASK MIKE FIRST, EVERY TIME. This takes most of the machine for hours and he
# works on it. It is not a background chore an agent may start on its own
# judgement, and "the box looks idle" is not the same question -- a desktop in
# use looks idle to pgrep. Set STORE_RUN_OK=1 to say he agreed.
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
RETRY=${RETRY:-}          # RETRY=1 also takes what a previous pass timed out on
DIR=out/store
mkdir -p "$DIR/logs"

[ -n "${STORE_RUN_OK:-}" ] || {
  cat >&2 <<'MSG'
refusing to start: this run takes most of the machine for hours.
Ask Mike, then re-run with STORE_RUN_OK=1 in front of the command.
MSG
  exit 1
}

[ -f out/census/parts.txt ] || { echo "need out/census/parts.txt"; exit 1; }
[ -f "$DIR/order.txt" ] || sort -R out/census/parts.txt > "$DIR/order.txt"
TOTAL=$(wc -l < "$DIR/order.txt" | tr -d ' ')

for i in $(seq 0 $((SHARDS - 1))); do
  awk -v n="$SHARDS" -v i="$i" 'NR % n == i' "$DIR/order.txt" > "$DIR/shard-$i.txt"
done

for i in $(seq 0 $((SHARDS - 1))); do
  nohup .venv/bin/python scripts/build-render-store.py \
    --list "$DIR/shard-$i.txt" --sources "$SOURCES" --timeout "$TIMEOUT" \
    ${RETRY:+--retry-failed} \
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
