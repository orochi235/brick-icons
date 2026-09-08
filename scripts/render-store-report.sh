#!/bin/sh
# Where the render store run has got to.
set -eu
cd "$(dirname "$0")/.."
DIR=out/store
printf 'shards running: %s\n' "$(pgrep -f build-render-store.py | wc -l | tr -d ' ')"
printf 'renders on disk: %s\n' "$(find renders -name '*.svg' 2>/dev/null | wc -l | tr -d ' ')"
.venv/bin/python - "$DIR" <<'PYEOF'
import collections, json, sys, glob, os
rows = []
for f in sorted(glob.glob(os.path.join(sys.argv[1], "s*.jsonl.*"))):
    if f.endswith(".inflight"):
        continue
    for line in open(f):
        if line.strip():
            rows.append(json.loads(line))
if not rows:
    print("no rows yet"); raise SystemExit
states = collections.Counter(r.get("error") or r.get("state") for r in rows)
total = sum(int(open(p).read().count("\n")) for p in glob.glob(os.path.join(sys.argv[1], "shard-*.txt")))
secs = [r["secs"] for r in rows if "secs" in r]
print(f"attempted {len(rows)} of {total} ({100*len(rows)/max(total,1):.1f}%)")
for state, n in states.most_common():
    print(f"  {state}: {n}")
if secs:
    secs.sort()
    print(f"  median {secs[len(secs)//2]:.1f}s, mean {sum(secs)/len(secs):.1f}s")
    left = total - len(rows)
    print(f"  ~{left * (sum(secs)/len(secs)) / 3600 / max(1, len(glob.glob(os.path.join(sys.argv[1], 'shard-*.txt')))):.1f}h left at this rate")
PYEOF
