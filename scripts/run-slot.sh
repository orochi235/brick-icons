#!/usr/bin/env bash
# Launch a fleet job and wire its returns home in the same command.
#
#     scripts/run-slot.sh --detach --timeout 12h --in brick-icons \
#       --task slot-occt-r7 --out out/slot-occt-r7 --to out/slot-occt-r7 \
#       --env PATH=... studio -- scripts/census-batch.sh occt 300 out/slot-occt-r7 {}
#
# Everything after the wrapper's own flags is passed to `onto run` untouched, so
# this forks no launch interface: a flag onto grows works here the day it lands.
#
# `--to` records a destination and onto pushes to it as the job writes -- when it
# works. On 2026-09-11 seven jobs held 10,000 files on their nodes with one file
# delivered each, so the controller-side pull is what actually gets results home.
# Hence both instruments start by default. `--no-stream` and `--no-watch` opt out.
#
# `--sync-from DIR` sends the node DIR's tree -- a clean worktree at HEAD --
# instead of this checkout's. Several sessions share this checkout, and a dirty
# one always ships its edits, which may be another session's unfinished engine.
# The returns still land here, where corpus.db is.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
stream=1
watch=1
# A refresh redraws parts the slot already holds, and the watcher skips those
# unless told to replace them -- a 7,379-part re-render once landed and indexed
# as nothing. `--overwrite` here is the watcher's flag, named at the launch.
watch_flags=(--overwrite-requested)
SRC=$ROOT
while [ $# -gt 0 ]; do
  case $1 in
    --sync-from) SRC=$(cd "$2" && pwd); shift 2 ;;
    --no-stream) stream=0; shift ;;
    --no-watch)  watch=0;  shift ;;
    --overwrite) watch_flags+=(--overwrite); shift ;;
    *) break ;;
  esac
done

[ $# -gt 0 ] || { echo "usage: $0 [--no-stream] [--no-watch] [--overwrite] [--sync-from DIR] <onto run args...>" >&2; exit 2; }

task=""; to=""; detach=0
args=("$@")
i=0
while [ $i -lt ${#args[@]} ]; do
  case ${args[$i]} in
    --task)    task=${args[$((i+1))]:-} ;;
    --task=*)  task=${args[$i]#--task=} ;;
    --to)      to=${args[$((i+1))]:-} ;;
    --to=*)    to=${args[$i]#--to=} ;;
    --detach)  detach=1 ;;
  esac
  i=$((i+1))
done

# A delivery recorded against a job id stops matching when the job is relaunched;
# keyed on the task it survives. Both instruments follow the task, so without one
# there is nothing to follow and the job would deliver into silence.
[ -n "$task" ] || { echo "run-slot: --task is required; the stream and the watcher both key on it" >&2; exit 2; }
[ -n "$to" ]   || { echo "run-slot: --to is required; it names the tree the watcher reads" >&2; exit 2; }

# Every row carries the build that drew it, and a slot counts a part as stale
# when that build predates the engine's last change. A node whose tree trails
# HEAD therefore spends its whole run drawing parts that land still stale:
# on 2026-09-13 studio sat 36 commits behind and nothing said so.
tree=$(basename "$ROOT"); nodes=(); prev=""
for a in "${args[@]}"; do
  case $prev in
    --in|-in)     tree=$a ;;
    --with|-with) IFS=, read -ra helpers <<< "$a"; nodes+=("${helpers[@]}") ;;
  esac
  case $a in
    --in=*|-in=*)     tree=${a#*=} ;;
    --with=*|-with=*) IFS=, read -ra helpers <<< "${a#*=}"; nodes+=("${helpers[@]}") ;;
    --any|-any) echo "run-slot: --any hides the node, so its tree revision cannot be checked; name the node" >&2; exit 2 ;;
    --) nodes+=("$prev"); break ;;
  esac
  prev=$a
done

build_of() {  # node, or empty for this checkout
  local py='import brick_icons; print(brick_icons.build())'
  if [ -z "$1" ]; then
    (cd "$SRC" && "$ROOT/.venv/bin/python" -c "$py")
  else
    onto run -in "$tree" "$1" -- .venv/bin/python -c "$py" 2>&1 | grep -E '^[0-9]+\.[0-9a-f]+\+?$' | tail -1 || true
  fi
}

want=$(build_of "")
for node in "${nodes[@]}"; do
  have=$(build_of "$node")
  # A job already holding the node's tree refuses the probe, and pipefail used
  # to end the launch here with no output at all.
  [ -n "$have" ] || { echo "run-slot: could not read $node:$tree's build -- is a job holding the tree? (onto jobs)" >&2; exit 1; }
  # A dirty label cannot tell two different sets of uncommitted edits apart, so
  # a dirty checkout always ships.
  if [ "$have" != "$want" ] || [ "${want%+}" != "$want" ]; then
    echo "run-slot: $node:$tree draws as ${have:-unknown}, this checkout as $want; syncing"
    (cd "$SRC" && onto sync -in "$tree" "$node") || { echo "run-slot: sync to $node refused; not launching" >&2; exit 1; }
    have=$(build_of "$node")
    if [ "$have" != "$want" ]; then
      echo "run-slot: $node still draws as ${have:-unknown} after sync; not launching" >&2
      # A node fetches its base commit from the remote and takes the rest as a
      # patch, so its build names the last pushed commit, never an unpushed one.
      ahead=$(git -C "$SRC" rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)
      [ "$ahead" = "0" ] || echo "run-slot: this checkout is $ahead commit(s) ahead of its upstream; push, then launch again" >&2
      exit 1
    fi
  fi
  echo "run-slot: $node:$tree at $have"
done

echo "run-slot: launching $task"
# `--to`, `--out` and the watcher's tree are relative paths, and resolving them
# against wherever this was called from once delivered a whole job into a
# worktree that had no corpus.db.
cd "$ROOT"
onto run "$@"

if [ $detach -eq 0 ]; then
  echo "run-slot: not --detach, so the job already ran to completion; nothing to stream"
  exit 0
fi

mkdir -p "$ROOT/out"

if [ $stream -eq 1 ]; then
  if pgrep -f "onto fetch.*$task" >/dev/null 2>&1; then
    echo "run-slot: a stream is already following $task; leaving it alone"
  else
    nohup onto fetch --stream "$task" > "$ROOT/out/fetch-$task.log" 2>&1 &
    echo "run-slot: streaming returns  pid $!  out/fetch-$task.log"
  fi
else
  echo "run-slot: --no-stream; nothing will pull $task home"
fi

if [ $watch -eq 1 ]; then
  if pgrep -f "ingest-watch.py.*$to" >/dev/null 2>&1; then
    echo "run-slot: a watcher is already reading $to; leaving it alone"
  else
    nohup "$ROOT/.venv/bin/python" "$ROOT/scripts/ingest-watch.py" "$to" \
      --every 300 --until "$task" "${watch_flags[@]}" \
      > "$ROOT/out/ingest-watch-$task.log" 2>&1 &
    echo "run-slot: ingesting as it lands  pid $!  out/ingest-watch-$task.log"
  fi
else
  echo "run-slot: --no-watch; $to will not reach corpus.db or the wall"
fi
