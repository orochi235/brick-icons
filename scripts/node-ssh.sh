#!/bin/sh
# Print the host to ssh/scp/rsync to for an onto node. An onto name is not an
# ssh name: msb-uai is `uai` in ~/.ssh/config and teitou is in it not at all,
# while every node's enrolled address (studio.local:7423) resolves.
#
#   scripts/node-ssh.sh msb-uai     # -> msb-uai.local
set -e
[ -n "$1" ] || { echo "usage: $0 <node>" >&2; exit 2; }
host=$(onto nodes | awk -v n="$1" '$1 == n { sub(/:[0-9]+$/, "", $3); print $3 }')
[ -n "$host" ] || { echo "node-ssh: $1 is not an enrolled node" >&2; exit 1; }
echo "$host"
