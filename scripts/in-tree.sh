#!/bin/sh
# Run a command in a named onto tree (`onto run --in <name>`), which a sync
# creates without vendor/ldraw or .venv: link both from the node's main copy
# first, after the sync that would otherwise delete them.
#
#   onto run --in bi-x msb-uai -- sh scripts/in-tree.sh .venv/bin/python -m pytest -q tests/test_occt.py
set -e
main="${ONTO_MAIN_TREE:-${ONTO_WORK:-$HOME/.config/onto/work}/brick-icons}"
mkdir -p vendor
[ -e vendor/ldraw ] || ln -sfn "$main/vendor/ldraw" vendor/ldraw
[ -e .venv ] || ln -sfn "$main/.venv" .venv
exec "$@"
