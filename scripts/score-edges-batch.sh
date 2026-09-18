#!/bin/sh
# Score one chunk of stored drawings against the edges their parts declare.
# Called once per line of a chunk index by onto's item dispatch:
#
#     onto run --detach --in brick-icons --each out/edges/chunks/naive.idx \
#       --task edge-score-naive studio -- \
#       scripts/score-edges-batch.sh naive {} out/edges/jsonl
#
# One JSONL per chunk, named for the chunk. Chunks sharing a JSONL would
# interleave their appends and corrupt each other's rows -- the same reason
# census-batch.sh gives for a JSONL per batch. `--skip-done` makes a relaunch
# under the same task step over what already landed.
set -eu
cd "$(dirname "$0")/.."
source=${1:?slot the drawings were filed under}
chunk=${2:?file of SVG paths, one per line}
dir=${3:-out/edges/jsonl}

mkdir -p "$dir"
name=$(basename "$chunk" .txt)
exec .venv/bin/python scripts/score-declared-edges.py \
  --source "$source" --list "$chunk" --jsonl "$dir/$source-$name.jsonl" \
  --skip-done
