"""One redraw: ask the spot worker, store what it drew, say so, then bring the
wall's sheets up to date in the background.

Every outcome is a `state` the lightbox reads: stored, unchanged, none,
failed or down. An ask the lab refuses before calling is the route's
business, not this module's.

A stored drawing is announced as `changed` before its sheets are touched:
re-encoding a slot's sheets takes seconds, and the drawing, its tiles and the
wall's cell poll do not wait on them. `sheets` follows once they are patched.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import db, goldens, spot_protocol, thumbs
from .. import requests as render_requests
from .events import Broker
from .spot import SpotDown, SpotError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Where:
    corpus_db: Path
    root: Path
    thumbs_root: Path
    requests_path: Path
    #: Where a reply's SVG waits to be copied into the store; emptied as it goes.
    scratch: Path


class SheetPatches:
    """Background sheet patches, one at a time per slot: two redraws in one
    slot patch its sheets in the order they were stored, and neither holds a
    request open while it does."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._slots: dict[str, ThreadPoolExecutor] = {}

    def submit(self, source: str, work: Callable[[], None]) -> Future:
        with self._lock:
            pool = self._slots.get(source)
            if pool is None:
                pool = self._slots[source] = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"sheets-{source}")
            return pool.submit(work)

    def shutdown(self) -> None:
        """Finish every patch already asked for, then stop."""
        with self._lock:
            pools, self._slots = list(self._slots.values()), {}
        for pool in pools:
            pool.shutdown(wait=True)


def redraw(part: str, source: str, spot, events: Broker, where: Where,
           patches: SheetPatches) -> dict:
    commit, want = spot.expected()
    render_requests.add(where.requests_path, part, source, build=want)
    request = spot_protocol.request(part, source, db.canonical_argv(part, source),
                                    build=want)
    try:
        reply = spot.draw(request, commit)
    except SpotDown as e:
        return {"state": "down", "detail": str(e)}
    except SpotError as e:
        return {"state": "failed", "error": e.error, "detail": str(e)}
    conn = db.connect(where.corpus_db)
    try:
        run_id = db.spot_run(conn, reply["build"], part, source)
        try:
            answer, dest = _take(conn, run_id, part, source, reply, where)
        finally:
            db.finish_run(conn, run_id)
    finally:
        conn.close()
    if answer["state"] == "stored":
        events.publish("changed", {"part": part, "source": source,
                                   "sha": answer["sha"],
                                   "build": reply["build"]})
        patches.submit(source, lambda: _patch_wall(part, source, dest,
                                                   answer["sha"], events, where))
    return answer


def _take(conn, run_id: int, part: str, source: str, reply: dict,
          where: Where) -> tuple[dict, Path | None]:
    tried = {"part": part, "source": source, "secs": reply["secs"],
             "error": reply["error"], "detail": reply["detail"]}
    said = {"secs": reply["secs"], "build": reply["build"]}
    if reply["error"] is not None:
        db.record_attempt(conn, run_id, {**tried, "state": None})
        return {"state": "failed", "error": reply["error"],
                "detail": reply["detail"], **said}, None
    if reply["state"] == "none":
        db.record_attempt(conn, run_id, {**tried, "state": "none"})
        return {"state": "none", **said}, None
    data = reply["svg"].encode()
    sha = goldens.sha256(data)
    held = conn.execute("SELECT sha256 FROM renders WHERE part_id = ? "
                        "AND source = ?", (part, source)).fetchone()
    db.record_attempt(conn, run_id, {**tried, "state": "stored"})
    if held is not None and held["sha256"] == sha:
        db.touch_render(conn, part, source)
        return {"state": "unchanged", "sha": sha, **said}, None
    where.scratch.mkdir(parents=True, exist_ok=True)
    made = where.scratch / f"{part}.{source}.svg"
    made.write_bytes(data)
    try:
        dest = db.store_render(conn, part, source, made, root=where.root,
                               run_id=run_id)
    finally:
        made.unlink(missing_ok=True)
    return {"state": "stored", "sha": sha, **said}, dest


def _patch_wall(part: str, source: str, dest: Path, sha: str,
                events: Broker, where: Where) -> None:
    """The part's tiles, then its cell on the slot's sheets and their masks,
    then `sheets`. A failure is a warning: the drawing is stored, and the
    next full bake draws the sheets from the store."""
    slot = where.thumbs_root / source
    try:
        conn = db.connect(where.corpus_db)
        try:
            index = conn.execute("SELECT count(*) FROM parts WHERE id < ?",
                                 (part,)).fetchone()[0]
            count = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
        finally:
            conn.close()
        thumbs.bake_part(part, dest, slot, sha)
        versions = thumbs.patch_cell(slot, part, index, count)
        masks = slot / thumbs.MASK_DIR
        if thumbs.has_sheets(masks):
            thumbs.patch_cell(masks, part, index, count)
    except Exception as e:                              # noqa: BLE001
        log.warning("%s in %s is stored, but its sheets were not patched "
                    "(%s: %s); the next bake repairs them",
                    part, source, type(e).__name__, e)
        return
    events.publish("sheets", {"part": part, "source": source,
                              "versions": {str(level): v
                                           for level, v in versions.items()}})
