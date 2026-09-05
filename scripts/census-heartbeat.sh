#!/bin/sh
# One line every INTERVAL seconds saying how far the census has got, on stdout
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
INTERVAL=${1:-300}
TOTAL=$(wc -l < "$DIR/order.txt" | tr -d ' ')

rows() { cat "$DIR"/$1-s*.jsonl 2>/dev/null | wc -l | tr -d ' '; }

pn=$(rows naive); po=$(rows occt)
printf '%s  watching %s parts per engine, every %ss\n' "$(date '+%F %H:%M')" "$TOTAL" "$INTERVAL"
while :; do
  sleep "$INTERVAL"
  n=$(rows naive); o=$(rows occt)
  printf '%s  naive %s/%s (%s%%) +%s   occt %s/%s (%s%%) +%s   %s shards   load %s\n' \
    "$(date '+%F %H:%M')" \
    "$n" "$TOTAL" "$((n * 100 / TOTAL))" "$((n - pn))" \
    "$o" "$TOTAL" "$((o * 100 / TOTAL))" "$((o - po))" \
    "$(pgrep -f compare-silhouette-truth | wc -l | tr -d ' ')" \
    "$(uptime | sed 's/.*averages*: *//' | cut -d' ' -f1)"
  pn=$n; po=$o
done
