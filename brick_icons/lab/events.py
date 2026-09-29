"""Things that happened in the lab, told to every open page.

Published from route threads, streamed as server-sent events, which a page
acts on at once instead of waiting for its next poll: `changed` when a redraw
is stored, and `sheets` when its slot's sheets have been patched to match.
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

#: Events held per subscriber while unread. A stalled client would otherwise
#: grow its queue forever; the page's own 10s cell poll recovers a dropped
#: event, so dropping the oldest is safe.
SUBSCRIBER_QUEUE_CAP = 256

Listener = Callable[[str, dict], None]


def _offer(queue: asyncio.Queue, item: tuple[str, dict]) -> None:
    """Queue `item`, dropping the oldest waiting event if `queue` is full."""
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass


#: Queued to a stream when its broker closes, ending it.
_CLOSED = ("", {})


class Broker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: list[Listener] = []
        self._closers: list[Callable[[], None]] = []
        self._closed = False

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

    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def on_close(self, closer: Callable[[], None]) -> Callable[[], None]:
        """Call `closer` when the broker closes -- at once if it has."""
        with self._lock:
            closed = self._closed
            if not closed:
                self._closers.append(closer)
        if closed:
            closer()

        def stop() -> None:
            with self._lock:
                if closer in self._closers:
                    self._closers.remove(closer)
        return stop

    def close(self) -> None:
        """End every open stream. A server waits for open responses before
        it stops, and a stream never finishes by itself."""
        with self._lock:
            self._closed = True
            closers, self._closers = self._closers, []
        for closer in closers:
            try:
                closer()
            except Exception:                           # noqa: BLE001
                log.exception("closing an event stream failed")


def frame(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, sort_keys=True)}\n\n"


async def stream(broker: Broker,
                 disconnected: Callable[[], Awaitable[bool]]) -> AsyncIterator[str]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_CAP)
    stop = broker.subscribe(
        lambda kind, data: loop.call_soon_threadsafe(_offer, queue, (kind, data)))
    unclose = broker.on_close(
        lambda: loop.call_soon_threadsafe(_offer, queue, _CLOSED))
    try:
        if broker.closed():
            return
        yield ": connected\n\n"
        while not await disconnected():
            try:
                item = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is _CLOSED:
                return
            yield frame(*item)
    finally:
        unclose()
        stop()
