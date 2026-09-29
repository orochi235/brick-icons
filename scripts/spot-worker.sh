#!/usr/bin/env bash
# The spot render worker's service command: what `onto service up` runs, and
# runs again after every roll to a new commit and every crash.
#
#   onto service up brick-spot-render --in brick-icons-spot --prefer studio \
#     -- scripts/spot-worker.sh
#
# A roll is a forced reset that keeps ignored files: .venv and vendor/ldraw
# survive it, but a dependency change in the new commit does not install
# itself. Nothing but the worker's replies may reach stdout.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"   # uv, resvg, potrace (provision-node.sh)

[ -d vendor/ldraw/parts ] || {
  echo "spot-worker: no vendor/ldraw in $PWD; provision this tree" \
       "(DEVELOPING.md, Spot rendering)" >&2
  exit 1
}
uv sync --frozen --extra occt --extra census --extra lab >&2
exec .venv/bin/python -m brick_icons.spot_worker
