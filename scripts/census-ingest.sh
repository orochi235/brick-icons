#!/bin/sh
# Rebuild corpus.db from the census trees on an interval, while a census runs.
#
#     scripts/census-ingest.sh [interval_seconds]   # default 900
#
# Every census tree under out/ is indexed, so a facet launched later needs no
# edit here -- db.census_trees finds it and db.census_source decides whether it
# is its own source or another run of the base census.
#
# Builds into a temp file and swaps it in, because db.rebuild deletes and
# rewrites: a lab reading the database mid-pass otherwise sees a half-built
# one. The temp database is checkpointed first -- both are WAL, and moving a
# fresh database over a stale corpus.db-wal hands sqlite a log that does not
# belong to it.
set -eu
cd "$(dirname "$0")/.."
EVERY=${1:-900}
DB=${DB:-corpus.db}

while :; do
  tmp="$DB.ingest.$$"
  rm -f "$tmp" "$tmp-wal" "$tmp-shm"
  if .venv/bin/python scripts/build-corpus-db.py --out "$tmp" >/dev/null 2>&1; then
    sqlite3 "$tmp" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null
    rm -f "$DB-wal" "$DB-shm"
    mv -f "$tmp" "$DB"
    rm -f "$tmp-wal" "$tmp-shm"
    # Indexing a render does not put it on the wall -- the wall draws baked
    # sheets. Idempotent by render sha, so this costs only the new parts.
    .venv/bin/python scripts/bake-thumbs.py >/dev/null 2>&1 || \
      echo "$(date '+%H:%M:%S') bake failed; the database is current, the sheets are not" >&2
    echo "$(date '+%H:%M:%S') $(sqlite3 "$DB" \
      "SELECT group_concat(s, ', ') FROM (SELECT source || ' ' || count(*) AS s
       FROM renders WHERE source LIKE 'census-white%' GROUP BY source)")"
  else
    # Keep the database that is already there: a failed pass is a pass to skip,
    # not a reason to leave the lab with nothing to read.
    echo "$(date '+%H:%M:%S') rebuild failed, kept the last database" >&2
    rm -f "$tmp" "$tmp-wal" "$tmp-shm"
  fi
  sleep "$EVERY"
done
