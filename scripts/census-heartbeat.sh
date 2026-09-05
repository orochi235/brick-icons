#!/bin/sh
# Progress every INTERVAL seconds on stdout: two `onto: progress` lines that
# `onto top` turns into bars, then one human line saying how far it has got,
# so whatever launched this owns the log. Run it as an onto job beside the
# shards:
#
#     onto run --detach --timeout 10h --in brick-icons <node> \
#       -- <tree>/scripts/census-heartbeat.sh 300
#
# A census runs for hours and its own logs are eight interleaved streams, so
# the only cheap way to answer "is it still moving" is to write the answer
# down periodically. Rows counted rather than parts rendered: a TimeoutError
# row is progress too, and a stalled rate is the thing worth seeing.
set -eu
cd "$(dirname "$0")/.."
DIR=out/census
INTERVAL=${1:-30}
TOTAL=$(wc -l < "$DIR/order.txt" | tr -d ' ')

# Every shard file for the engine, whatever the split is called: census-reshard.py
# renames them, and a glob pinned to one naming freezes the count silently.
rows() { cat "$DIR"/"$1"-*.jsonl 2>/dev/null | wc -l | tr -d ' '; }

pn=$(rows naive); po=$(rows occt)
printf '%s  watching %s parts per engine, every %ss\n' "$(date '+%F %H:%M')" "$TOTAL" "$INTERVAL"
while :; do
  sleep "$INTERVAL"
  n=$(rows naive); o=$(rows occt)
  # onto top draws a bar from these; see `onto top -h` for the contract.
  printf 'onto: progress %s/%s naive\n' "$n" "$TOTAL"
  printf 'onto: progress %s/%s occt\n' "$o" "$TOTAL"
  printf '%s  naive %s/%s (%s%%) +%s   occt %s/%s (%s%%) +%s   %s shards   load %s\n' \
    "$(date '+%F %H:%M')" \
    "$n" "$TOTAL" "$((n * 100 / TOTAL))" "$((n - pn))" \
    "$o" "$TOTAL" "$((o * 100 / TOTAL))" "$((o - po))" \
    "$(pgrep -f compare-silhouette-truth | wc -l | tr -d ' ')" \
    "$(uptime | sed 's/.*averages*: *//' | cut -d' ' -f1)"
  pn=$n; po=$o
done
