"""Background work, with progress the client can watch.

A per-item failure is an event rather than a raised error: a batch with two bad
parts is a partial success, and stopping the run would throw away the rest.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable


class Registry:
    """Jobs this process is running, by id."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, items: list, work: Callable) -> str:
        """Run `work(item, emit)` over `items` on a thread. Whatever `work`
        returns is collected into the job's `results`, which is how a caller
        gets an answer back without closing over the not-yet-assigned id."""
        job_id = uuid.uuid4().hex[:12]
        record = {"id": job_id, "kind": kind, "state": "running",
                  "total": len(items), "done": 0, "failed": 0,
                  "events": [], "results": [], "cancel": threading.Event(),
                  "started": time.time()}
        with self._lock:
            self._jobs[job_id] = record
        threading.Thread(target=self._run, args=(record, items, work),
                         daemon=True).start()
        return job_id

    def _run(self, record: dict, items: list, work: Callable) -> None:
        for index, item in enumerate(items, 1):
            if record["cancel"].is_set():
                record["state"] = "cancelled"
                return

            def emit(message, _i=index, _ok=True):
                record["events"].append({"index": _i, "total": record["total"],
                                         "message": str(message), "ok": _ok})

            try:
                result = work(item, emit)
                if result is not None:
                    record["results"].append(result)
                record["done"] += 1
            except Exception as e:                  # noqa: BLE001
                record["failed"] += 1
                emit(f"{type(e).__name__}: {e}", index, False)
        record["state"] = "done"

    def get(self, job_id: str) -> dict | None:
        record = self._jobs.get(job_id)
        if record is None:
            return None
        return {k: v for k, v in record.items() if k != "cancel"}

    def cancel(self, job_id: str) -> bool:
        record = self._jobs.get(job_id)
        if record is None:
            return False
        record["cancel"].set()
        return True
