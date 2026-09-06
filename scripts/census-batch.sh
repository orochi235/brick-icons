#!/bin/sh
# Measure one batch of parts. Called once per line of a batch list by onto's
# item dispatch:
#
#     onto run --detach --in brick-icons --each out/census/<list>.txt \
#       <node> -- scripts/census-batch.sh occt 120 out/census/occt-backfill.jsonl {}
#
# A batch rather than a part because `import cadquery` costs 6.2s and the
# median part 21.6s: one process per part would spend 8.1 hours starting
# interpreters over the 4,733-part backfill.
set -eu
cd "$(dirname "$0")/.."
engine=${1:?engine}
timeout=${2:?per-part timeout}
jsonl=${3:?jsonl}
batch=${4:?comma-separated part ids}
KEEP=${KEEP:-out/census/renders}

IFS=,
# shellcheck disable=SC2086
set -- $batch
unset IFS

exec .venv/bin/python scripts/compare-silhouette-truth.py "$@" \
  --engine "$engine" --timeout "$timeout" --jsonl "$jsonl" --skip-done --keep "$KEEP"
