"""One redraw: ask the spot worker, store what it drew, say so, then bring the
wall's sheets up to date in the background.

Every outcome is a `state` the lightbox reads: stored, unchanged, none,
failed or down. An ask the lab refuses before calling is the route's
business, not this module's.

A stored drawing's tiles are baked before it is announced as `changed`: the
wall fetches them under the new sha as soon as it hears, and would cache a
404 or the old tile under that key otherwise. Its cell on the slot's sheets
is patched off the request thread, since re-encoding them takes seconds, and
`sheets` follows once they are.
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
from .spot import CALL_TIMEOUT_S, SpotDown, SpotError

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
    request = spot_protocol.request(part, source, db.canonical_argv(part, source),
                                    build=want)
    try:
        reply = spot.draw(request, commit)
    except SpotDown as e:
        return {"state": "down", "detail": str(e)}
    except SpotError as e:
        if e.error != "TimeoutError":
            return {"state": "failed", "error": e.error, "detail": str(e)}
        # onto gave up waiting on the worker: an attempt that ran out of
        # time, as a worker's own timeout is.
        reply = spot_protocol.reply(secs=CALL_TIMEOUT_S, build=want,
                                    error=e.error, detail=str(e))
    # Recorded only now the worker was actually asked: a down service or a
    # failed roll tried nothing, so nothing was asked for.
    render_requests.add(where.requests_path, part, source, build=want)
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
        _bake_tiles(part, source, dest, answer["sha"], where)
        events.publish("changed", {"part": part, "source": source,
                                   "sha": answer["sha"],
                                   "build": reply["build"]})
        patches.submit(source, lambda: _patch_sheets(part, source, events,
                                                     where))
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
    if held is not None and held["sha256"] == sha:
        db.record_attempt(conn, run_id, {**tried, "state": "stored"})
        db.touch_render(conn, part, source)
        return {"state": "unchanged", "sha": sha, **said}, None
    where.scratch.mkdir(parents=True, exist_ok=True)
    made = where.scratch / f"{part}.{source}.svg"
    made.write_bytes(data)
    try:
        try:
            dest = db.store_render(conn, part, source, made, root=where.root,
                                   run_id=run_id)
        except Exception as e:
            db.record_attempt(conn, run_id,
                              {**tried, "state": None,
                               "error": type(e).__name__})
            raise
    finally:
        made.unlink(missing_ok=True)
    db.record_attempt(conn, run_id, {**tried, "state": "stored"})
    return {"state": "stored", "sha": sha, **said}, dest


def _bake_tiles(part: str, source: str, dest: Path, sha: str,
                where: Where) -> None:
    """The part's tiles and masks. A failure is a warning: the drawing is
    stored, and the next bake draws its tiles from the store."""
    try:
        thumbs.bake_part(part, dest, where.thumbs_root / source, sha)
    except Exception as e:                              # noqa: BLE001
        log.warning("%s in %s is stored, but its tiles were not baked "
                    "(%s: %s); the next bake repairs them",
                    part, source, type(e).__name__, e)


def _patch_sheets(part: str, source: str, events: Broker,
                  where: Where) -> None:
    """The part's cell on the slot's sheets, then on their masks, then
    `sheets` for whichever of them changed. A failure is a warning: the
    drawing is stored, and the next full bake draws the sheets from the
    store."""
    slot = where.thumbs_root / source
    versions = {}
    try:
        conn = db.connect(where.corpus_db)
        try:
            index = conn.execute("SELECT count(*) FROM parts WHERE id < ?",
                                 (part,)).fetchone()[0]
            count = conn.execute("SELECT count(*) FROM parts").fetchone()[0]
        finally:
            conn.close()
        versions = thumbs.patch_cell(slot, part, index, count)
        masks = slot / thumbs.MASK_DIR
        if thumbs.has_sheets(masks):
            thumbs.patch_cell(masks, part, index, count)
    except Exception as e:                              # noqa: BLE001
        log.warning("%s in %s is stored, but its sheets were not patched "
                    "(%s: %s); the next bake repairs them",
                    part, source, type(e).__name__, e)
    if versions:
        events.publish("sheets", {"part": part, "source": source,
                                  "versions": {str(level): v
                                               for level, v in versions.items()}})
