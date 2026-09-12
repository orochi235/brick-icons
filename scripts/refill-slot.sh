#!/usr/bin/env bash
# Draw whatever a slot is still missing, sized and listed at launch time.
#
#     scripts/refill-slot.sh white-naive studio slot-white-naive-tail
#     scripts/refill-slot.sh occt msb-uai slot-occt-r8 --budget 6 --workers 10
#
# The list is the point. A batch written now and launched in six hours asks a
# node to redraw everything that landed in between, so this recomputes the gap,
# copies the list to the node and launches in one step -- which is what makes it
# safe behind `queue-after.sh`:
#
#     scripts/queue-after.sh <job-id> -- scripts/refill-slot.sh white-naive \
#       studio slot-white-naive-tail
#
# ENGINE, SOURCE and EXTRA are read from slot-coverage's own output rather than
# typed here: EXTRA is derived from `db._CANONICAL` through the CLI's parser, and
# a slot's flags spelled from memory draw a different slot under the right name.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

slot=${1:?usage: refill-slot.sh <slot> <node> <task> [options]}
node=${2:?usage: refill-slot.sh <slot> <node> <task> [options]}
task=${3:?usage: refill-slot.sh <slot> <node> <task> [options]}
shift 3

budget=6
workers=8
timeout=12h
only=all
cap=300
while [ $# -gt 0 ]; do
  case $1 in
    --budget)  budget=$2; shift 2 ;;
    --workers) workers=$2; shift 2 ;;
    --timeout) timeout=$2; shift 2 ;;
    --only)    only=$2; shift 2 ;;
    --cap)     cap=$2; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done

dir=out/$task
list=$dir/batches.txt
mkdir -p "$dir"

# Its own directory, never the earlier pass's: a batch JSONL is named for its
# first part, so a second pass starting on a part that began an earlier batch
# appends to that file -- and `--skip-done` then reads the old timeout rows as
# done and skips exactly the parts being redrawn.
survey=$(.venv/bin/python scripts/slot-coverage.py --slot "$slot" \
    --budget "$budget" --workers "$workers" --only "$only" --out "$list")
echo "$survey"

engine=$(printf '%s\n' "$survey" | sed -n 's/^  ENGINE=//p')
source=$(printf '%s\n' "$survey" | sed -n 's/^  SOURCE=//p')
extra=$(printf '%s\n' "$survey" | sed -n "s/^  EXTRA='\(.*\)'$/\1/p")
[ -n "$engine" ] && [ -n "$source" ] || {
  echo "slot-coverage printed no ENGINE/SOURCE; nothing launched" >&2; exit 1; }
[ -s "$list" ] || { echo "$slot has nothing left to draw" >&2; exit 1; }

parts=$(tr ',' '\n' < "$list" | grep -c .)
echo "launching $parts parts of $slot on $node as $task, ${cap}s cap"

# `--each` reads the list in the node's own tree and out/ is gitignored, so it
# has to be copied -- and the directory does not exist there either. Skipping
# this leaves a job that dies in seconds with an empty log.
ssh "$node" "mkdir -p ~/.config/onto/work/brick-icons/$dir"
scp -q "$list" "$node:.config/onto/work/brick-icons/$list"

# The watchdog has to stay above the measurement cap. It kills a part that has
# been in flight longer than HARD and records it as ProcessDied, so a default
# 240s watchdog under a 900s cap buries every part the longer cap was raised to
# reach -- as a crash, which reads as a different fault entirely.
hard=$(( cap + 300 ))

exec scripts/run-slot.sh --detach --timeout "$timeout" --in brick-icons \
  --task "$task" --each "$list" --workers "$workers" --retries 1 \
  --env PATH=/Users/mike/.local/bin:/opt/homebrew/bin:/usr/bin:/bin \
  --env "SOURCE=$source" --env "KEEP=$dir/renders" --env "EXTRA=$extra" \
  --env "HARD=$hard" \
  --out "$dir" --to "$dir" \
  "$node" -- scripts/census-batch.sh "$engine" "$cap" "$dir" {}
