#!/bin/sh
# Snapshot corpus.db with sqlite's own VACUUM INTO.
#
#     scripts/snap-corpus.sh [dest]
#
# A second on a 73M database, WAL-consistent under a running lab server, and it
# compacts as it copies. This is what makes deleting an ingested log safe: the
# rows are then in two files rather than one that gets dropped and rebuilt.
set -eu
cd "$(dirname "$0")/.."
DB=${DB:-corpus.db}
dest=${1:-out/snapshots/corpus-$(date '+%Y%m%d-%H%M')-$(git rev-parse --short HEAD).db}

if [ -e "$dest" ]; then
  echo "refusing to overwrite $dest" >&2
  exit 1
fi
mkdir -p "$(dirname "$dest")"
sqlite3 "$DB" "VACUUM INTO '$dest'"
ls -lh "$dest"
