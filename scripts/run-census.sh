#!/bin/sh
# Silhouette-truth census over the unprinted library, both engines, sharded.
#
#     scripts/run-census.sh [shards_per_engine] [per_part_timeout_s]
#
# Detached by design: a foreground call dies at the tool timeout no matter what
# the process is doing. Each shard streams JSONL and resumes with --skip-done,
# so re-running this picks up where the night stopped.
set -eu
cd "$(dirname "$0")/.."
SHARDS=${1:-4}
TIMEOUT=${2:-120}
DIR=out/census
mkdir -p "$DIR/logs"

[ -f "$DIR/parts.txt" ] || .venv/bin/python - "$DIR/parts.txt" <<'PYLIST'
# The census corpus: every library part whose description line says it is a
# real, current part -- no print, no sticker, no ~alias and no _shortcut.
import re, sys
from pathlib import Path
keep = []
for f in sorted(Path("vendor/ldraw/parts").glob("*.dat")):
    t = re.sub(r"^0\s*", "", f.open(errors="ignore").readline()).strip()
    if t and not t.startswith(("~", "_")) and not re.search(r"\b(pattern|sticker)\b", t, re.I):
        keep.append(f.stem)
Path(sys.argv[1]).write_text("\n".join(keep) + "\n")
print(f"corpus: {len(keep)} parts")
PYLIST
[ -f "$DIR/order.txt" ] || sort -R "$DIR/parts.txt" > "$DIR/order.txt"
TOTAL=$(wc -l < "$DIR/order.txt" | tr -d ' ')

for i in $(seq 0 $((SHARDS - 1))); do
  awk -v n="$SHARDS" -v i="$i" 'NR % n == i' "$DIR/order.txt" > "$DIR/shard-$i.txt"
done

for engine in naive occt; do
  for i in $(seq 0 $((SHARDS - 1))); do
    nohup .venv/bin/python scripts/compare-silhouette-truth.py \
      --list "$DIR/shard-$i.txt" --engine "$engine" --timeout "$TIMEOUT" \
      --jsonl "$DIR/$engine-s$i.jsonl" --skip-done \
      > "$DIR/logs/$engine-s$i.log" 2>&1 &
    echo "started $engine shard $i (pid $!)"
  done
done

{
  echo "# Census run $(date '+%Y-%m-%d %H:%M')"
  echo
  echo "- commit: $(git rev-parse --short HEAD) ($(git rev-parse --abbrev-ref HEAD))"
  echo "- corpus: $TOTAL unprinted parts, shuffled into $SHARDS shards per engine"
  echo "- per-part cap: ${TIMEOUT}s"
  echo
  echo "Progress: .venv/bin/python scripts/census-report.py"
} >> "$DIR/RUN.md"
echo "--- $DIR/RUN.md updated; watch with: scripts/census-report.py"
