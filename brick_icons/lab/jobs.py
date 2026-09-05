"""Background work, with progress the client can watch.

A per-item failure is an event rather than a raised error: a batch with two bad
parts is a partial success, and stopping the run would throw away the rest.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class Registry:
    """Jobs this process is running, by id."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, items: list, work: Callable,
              workers: int = 1) -> str:
        """Run `work(item, emit, cancel)` over `items` on a thread. Whatever
        `work` returns is collected into the job's `results`, which is how a
        caller gets an answer back without closing over the not-yet-assigned
        id. `cancel` is the job's own event: an item long enough to be worth
        cancelling has to watch it, because the loop only checks between
        items. `workers` is how many items may be in flight at once: a
        sheet of many renders left at 1 uses one render slot of four."""
        job_id = uuid.uuid4().hex[:12]
        record = {"id": job_id, "kind": kind, "state": "running",
                  "total": len(items), "done": 0, "failed": 0,
                  "events": [], "results": [], "cancel": threading.Event(),
                  "started": time.time()}
        with self._lock:
            self._jobs[job_id] = record
        threading.Thread(target=self._run,
                         args=(record, items, work, max(1, workers)),
                         daemon=True).start()
        return job_id

    def _run(self, record: dict, items: list, work: Callable,
             workers: int) -> None:
        counts = threading.Lock()

        def one(index: int, item) -> None:
            if record["cancel"].is_set():
                return

            def emit(message, _i=index, _ok=True):
                record["events"].append({"index": _i, "total": record["total"],
                                         "message": str(message), "ok": _ok})

            try:
                result = work(item, emit, record["cancel"])
                with counts:
                    if result is not None:
                        record["results"].append(result)
                    record["done"] += 1
            except Exception as e:                  # noqa: BLE001
                with counts:
                    record["failed"] += 1
                emit(f"{type(e).__name__}: {e}", index, False)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for index, item in enumerate(items, 1):
                pool.submit(one, index, item)
        record["state"] = "cancelled" if record["cancel"].is_set() else "done"

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
