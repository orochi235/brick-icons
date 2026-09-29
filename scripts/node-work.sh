#!/bin/sh
# Print where an onto node keeps its trees, for a script that reaches the node
# over ssh. `onto set --work-dir` can move them; an agent too old to say keeps
# them at the default.
#
#   scripts/node-work.sh keiei      # -> /Users/mike/.config/onto/work
set -e
[ -n "$1" ] || { echo "usage: $0 <node>" >&2; exit 2; }
dir=$(onto node "$1" --json | jq -r '.work_dir // empty')
echo "${dir:-.config/onto/work}"
