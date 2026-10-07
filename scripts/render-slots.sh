#!/usr/bin/env bash
# Draw parts under the silhouette and white slots of both engines, into
# <out>/<slot>-<engine>/. Meant to run on a fleet node through `onto do`.
#   scripts/render-slots.sh out/p6107 6107 [more parts...]
set -u
out=$1; shift
py=${PY:-.venv/bin/python}
mkdir -p "$out"
for part in "$@"; do
  for e in naive occt; do
    for s in silhouette white; do
      if [ "$s" = silhouette ]; then lw=0; style=flat3
      elif [ "$e" = occt ]; then lw=1.4; style=white
      else lw=2; style=white; fi
      t0=$(date +%s)
      "$py" -m brick_icons.cli "$part" --format svg --shading outline \
        --shade-style "$style" --angle iso --engine "$e" \
        --line-width "$lw" --silhouette-width "$lw" --out "$out/$s-$e"
      echo "$part $s-$e rc=$? $(( $(date +%s) - t0 ))s"
    done
  done
done
