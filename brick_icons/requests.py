"""Parts somebody asked a slot to draw again: part, slot, when, by whom, and
the build the redraw asked for.

A record, not a queue: every redraw is drawn at once by the spot worker. The
review queue links a displaced drawing to the ask that caused it
(`lab.review_api.linked_request`). An append-only JSONL log rather than a
`corpus.db` table, because `census-ingest.sh` rebuilds the database from the
render trees, and a request is in no tree.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import db

DEFAULT_PATH = Path("store-queue") / "requests.jsonl"

#: Slots drawn by LDView or a browser, which nothing in this repository runs.
#: `db.is_reference_slot` decides which those are, so a new reference slot
#: is refused without a second list to remember.
DRAWN_ELSEWHERE = tuple(s for s in db.SOURCES if db.is_reference_slot(s))


def add(path: Path | str, part: str, source: str, by: str = "lab",
        at: str | None = None, build: str | None = None) -> dict:
    """`build` is the one the redraw asked the worker to draw at."""
    record = {"part": part, "source": source, "at": at or db.now(), "by": by}
    if build is not None:
        record["build"] = build
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def load(path: Path | str) -> list[dict]:
    """Every request, oldest first. A torn last line from a writer that died
    mid-append is skipped rather than failing every reader."""
    path = Path(path)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict) and {"part", "source", "at"} <= r.keys():
            out.append(r)
    return out
