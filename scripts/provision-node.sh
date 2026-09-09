#!/usr/bin/env bash
# Make an onto node able to run this repo's jobs. Run it HERE, not there:
# the parts library and the two CLI tools are copied off this machine.
#
#   scripts/provision-node.sh keiei
#
# Idempotent, and safe to re-run after a `uv.lock` change.
#
# The LDraw library is COPIED rather than downloaded. complete.zip is a
# rolling snapshot -- the URL only ever serves the latest -- so a node that
# fetches its own gets a different library from this checkout and draws
# different pictures with no code change (see scripts/external-deps.lock).
set -euo pipefail
cd "$(dirname "$0")/.."

NODE="${1:-}"
[ -n "$NODE" ] || { echo "usage: $0 <node>" >&2; exit 2; }
TREE=".config/onto/work/$(basename "$PWD")"
REMOTE_BIN='$HOME/.local/bin'

step() { printf '\n== %s\n' "$1"; }

step "source -> $NODE:$TREE"
# The patch carries uncommitted and unpushed work; the node fetches the base
# from origin itself. -force lets the reset drop job output the node still
# holds, which is why this is a provisioning step and not a routine one.
onto sync -force "$NODE"

step "uv"
ssh "$NODE" 'test -x ~/.local/bin/uv \
  || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null; ~/.local/bin/uv --version'

step "python + dependencies"
# Every extra a fleet job has ever needed: occt is the engine under work,
# census brings scipy (a sync without it killed every worker on the import),
# and lab is what serves a node-side render.
ssh "$NODE" "cd $TREE && ~/.local/bin/uv sync --extra occt --extra census --extra lab \
  2>&1 | tail -3"

step "resvg + potrace"
# Version-matched to external-deps.lock by construction: they are this
# machine's binaries. potrace's dylib lives in the Cellar, so the copy is
# repointed at one beside it and re-signed ad-hoc.
ssh "$NODE" "mkdir -p $REMOTE_BIN \$HOME/.local/lib"
scp -q "$(command -v resvg)" "$NODE:.local/bin/resvg"
scp -q "$(command -v potrace)" "$NODE:.local/bin/potrace"
POTRACE_LIB=$(otool -L "$(command -v potrace)" | awk '/libpotrace/ {print $1}')
scp -q "$POTRACE_LIB" "$NODE:.local/lib/"
ssh "$NODE" "chmod +x $REMOTE_BIN/resvg $REMOTE_BIN/potrace
  install_name_tool -change '$POTRACE_LIB' \
    '@executable_path/../lib/$(basename "$POTRACE_LIB")' $REMOTE_BIN/potrace 2>/dev/null
  codesign -f -s - $REMOTE_BIN/potrace 2>/dev/null || true
  $REMOTE_BIN/resvg --version; $REMOTE_BIN/potrace --version | head -1"

step "LDraw library (612 MB, this checkout's snapshot)"
rsync -a vendor/ldraw/ "$NODE:$TREE/vendor/ldraw/"

step "verify"
# Draws a part rather than importing modules: an import proves the wheels
# landed, a render proves the library did too.
ssh "$NODE" "cd $TREE && .venv/bin/python -m brick_icons.cli 3941p01 --decal \
  --out /tmp/provision-check && ls -l /tmp/provision-check"
echo
echo "$NODE is provisioned. A later 'onto sync' does not touch vendor/, but"
echo "does reset job output the node holds."
