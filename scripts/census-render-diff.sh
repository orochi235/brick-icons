#!/usr/bin/env bash
# Byte-diff a part list's SVG between HEAD and another revision.
#
# The engines' output is supposed to be unchanged by a performance change, and
# "looks the same" is not a check -- this renders both sides in the census's own
# mode and compares bytes. Only the files a revision actually changes are
# swapped, so an unrelated commit landing meanwhile does not disturb the run.
#
#   scripts/census-render-diff.sh <base-rev> <part-list> [engine]
#
# Leaves the tree as it found it, including on failure.
set -euo pipefail

base=${1:?usage: census-render-diff.sh <base-rev> <part-list> [engine]}
list=${2:?usage: census-render-diff.sh <base-rev> <part-list> [engine]}
engine=${3:-occt}
work=$(mktemp -d)
files=$(git diff --name-only "$base" HEAD -- 'brick_icons/*.py')
[ -n "$files" ] || { echo "no brick_icons change between $base and HEAD" >&2; exit 1; }

# shellcheck disable=SC2086
restore() { git checkout -q HEAD -- $files; }
trap restore EXIT

render() {
    python - "$1" "$list" "$engine" <<'PY'
import sys, time
from pathlib import Path
from brick_icons import cli
out, listing, engine = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
out.mkdir(parents=True, exist_ok=True)
parts = [l.split('#')[0].strip() for l in open(listing)]
parts = [p for p in parts if p]
for i, p in enumerate(parts, 1):
    argv = [p, "--format", "svg", "--shading", "outline", "--shade-style",
            "flat3", "--angle", "iso", "--engine", engine, "--line-width", "0",
            "--silhouette-width", "0", "--out", str(out)]
    try:
        cfg = cli._config_from_args(cli.build_parser().parse_args(argv))
        t = time.perf_counter()
        cli.process_one(cfg, p, out)
        print(f"  {i}/{len(parts)} {p} {time.perf_counter() - t:.2f}s", flush=True)
    except BaseException as e:                      # a crash is a difference too
        (out / f"{p}.ERROR").write_text(type(e).__name__)
        print(f"  {i}/{len(parts)} {p} FAILED {type(e).__name__}", flush=True)
PY
}

echo "=== HEAD"
render "$work/head"
echo "=== $base ($(echo "$files" | tr '\n' ' '))"
# shellcheck disable=SC2086
git checkout -q "$base" -- $files
render "$work/base"
restore

echo "=== diff"
if diff -rq "$work/base" "$work/head"; then
    echo "BYTE-IDENTICAL ($(ls "$work/head" | grep -c '\.svg$') parts, $engine)"
else
    echo "DIFFERS -- renders kept in $work" >&2
    trap - EXIT
    exit 1
fi
rm -rf "$work"
