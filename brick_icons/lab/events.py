"""Things that happened in the lab, told to every open page.

Published from route threads, streamed as server-sent events. Only `changed`
for now -- a stored redraw -- which a page acts on at once instead of waiting
for its next poll.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import AsyncIterator, Awaitable, Callable

log = logging.getLogger(__name__)

#: Seconds between keepalive comments on an idle stream, so a proxy between
#: the page and the lab does not close it for silence.
KEEPALIVE_S = 15.0

Listener = Callable[[str, dict], None]


class Broker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def stop() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)
        return stop

    def publish(self, kind: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(kind, data)
            except Exception:                           # noqa: BLE001
                log.exception("an event listener failed on %s", kind)

    def listeners(self) -> int:
        with self._lock:
            return len(self._listeners)


def frame(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


async def stream(broker: Broker,
                 disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
    stop = broker.subscribe(
        lambda kind, data: loop.call_soon_threadsafe(queue.put_nowait, (kind, data)))
    try:
        yield ": connected\n\n"
        while not await disconnected():
            try:
                kind, data = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield frame(kind, data)
    finally:
        stop()
