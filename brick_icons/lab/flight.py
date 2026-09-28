"""One computation per question in flight, however many callers ask it.

Every route runs in a thread, and nothing cancels one whose client went away.
A page load that fans out into a slow query, repeated by a few reloads, used
to run that query once per caller; under load the copies starved each other
past a minute apiece.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Hashable


class _Flight:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None


class Flights:
    """`run(key, compute)` calls `compute` once for every caller that asks for
    `key` while an earlier call for it is still running; they all get its
    answer, or its exception. Nothing is kept once the flight lands -- holding
    an answer is the caller's decision, with its own invalidation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flying: dict[Hashable, _Flight] = {}

    def run(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        with self._lock:
            flight = self._flying.get(key)
            leader = flight is None
            if leader:
                flight = self._flying[key] = _Flight()
        if not leader:
            flight.done.wait()
            if flight.error is not None:
                raise flight.error
            return flight.result
        try:
            flight.result = compute()
            return flight.result
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            with self._lock:
                del self._flying[key]
            flight.done.set()
