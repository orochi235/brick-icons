#!/bin/sh
# Hold a launch until a detached onto job stops, then run it.
#
#     scripts/queue-after.sh <job-id> [--give-up <hours>] -- <command...>
#
# `onto jobs` lists only what is still running, so a job id falling off it is
# the signal. There is no "run after" in onto itself and a node's working tree
# takes one job at a time -- a launch made early dies on a 409 rather than
# queueing, which is the whole reason this exists.
set -eu

job=$1
shift
hours=24
if [ "${1:-}" = "--give-up" ]; then
    hours=$2
    shift 2
fi
[ "${1:-}" = "--" ] && shift

deadline=$(( $(date +%s) + hours * 3600 ))
echo "waiting on $job, giving up at $(date -r "$deadline" '+%H:%M %d %b')"
while onto jobs 2>/dev/null | awk '{print $1}' | grep -qx "$job"; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "$job still running at the deadline; not launching"
        exit 1
    fi
    sleep 120
done
echo "$job has stopped at $(date '+%H:%M:%S'); launching"
exec "$@"
