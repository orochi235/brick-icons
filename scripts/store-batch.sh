#!/bin/sh
# Render one batch of parts into the tracked store, in one process. Called
# once per line of a batch list by onto's item dispatch:
#
#     onto run --detach --in brick-icons --each out/census/batches.txt \
#       <node> -- scripts/store-batch.sh occt 120 out/store/r0 {}
#
# A batch rather than a part for the reason census-batch.sh gives: the engine
# import costs seconds and one process per part would spend hours starting
# interpreters. Lines are comma-separated part ids, as census-reshard.py
# writes them.
#
# Resumable at two levels: build-render-store.py skips a part that already has
# a file under renders/<source>/, and it skips one already in this batch's
# log. Re-running the job continues it.
set -eu
cd "$(dirname "$0")/.."
source=${1:?source}
timeout=${2:?per-part timeout}
dir=${3:?output dir}
line=${4:?comma-separated part ids}

mkdir -p "$dir"
set -- $(echo "$line" | tr ',' ' ')
# Named for its first part, like the census: two batches sharing one log would
# interleave their appends.
exec .venv/bin/python scripts/build-render-store.py \
    --sources "$source" --timeout "$timeout" \
    --log "$dir/$source-$1.jsonl" "$@"
