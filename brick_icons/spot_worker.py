"""The spot render worker: one warm process on the fleet that draws a part
the moment the lab asks.

onto runs it as a service through `scripts/spot-worker.sh` (DEVELOPING.md,
"Spot rendering"). Each pool process imports the engine once, then draws
every request it is handed in a forked child, through the CLI's own path and
under the batch per-part cap, so a redraw pays for the render and not for
Python starting up.
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import sys
import tempfile
import threading
from concurrent.futures import Executor, Future, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import IO, Callable

from . import batch, build, spot_protocol
from .lab import runner as lab_runner
from .lab import store

#: Redraws drawn at once; a third waits for one of them.
POOL = int(os.environ.get("BRICK_SPOT_POOL", "2"))
#: The render store's own cap (`scripts/build-render-store.py --mem-gb`).
MEM_GB = 8.0


def warm() -> None:
    """Pool initializer: the engine's imports, once per pool process. A forked
    request inherits them."""
    from . import cli, hlr  # noqa: F401
    try:
        from . import occt  # noqa: F401
    except ImportError:
        pass


def render(req: dict, timeout: float = batch.RENDER_TIMEOUT_S) -> dict:
    """One request's reply. Never raises: a part that fails is a reply
    saying so."""
    part, source, argv = req["part"], req["source"], list(req["argv"])
    # Removed here rather than by the child, which a timeout kills mid-render.
    scratch = Path(tempfile.mkdtemp(prefix="brick-spot-"))

    def work(item: str) -> dict:
        lab_runner.draw(argv, scratch)
        name = store.drawing_in(sorted(p.name for p in scratch.iterdir()), source)
        if name is None:
            return {"part": item, "state": "none", "svg": None}
        if not name.endswith(".svg"):
            raise RuntimeError(f"{source} drew {name}, which is not an SVG")
        return {"part": item, "state": "drawn",
                "svg": (scratch / name).read_text()}

    try:
        row = batch.Runner(None, timeout=timeout, key="part", isolate=True,
                           mem_gb=MEM_GB).call(part, work)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    failed = row.get("error") is not None
    return spot_protocol.reply(
        svg=None if failed else row.get("svg"), secs=row["secs"],
        build=build(), state=None if failed else row["state"],
        error=row.get("error"), detail=row.get("detail"))


def _failed(exc: BaseException) -> dict:
    return spot_protocol.reply(build=build(), error=type(exc).__name__,
                               detail=str(exc)[:300])


def serve(inp: IO[str], out: IO[str], pool: Executor,
          answer: Callable[[dict], dict]) -> None:
    """Answer every request on `inp` until it closes. A ping is answered
    here; a render goes to `pool`, so two draw at once with the default
    pool, and each reply is written as it finishes."""
    lock = threading.Lock()
    running: set[Future] = set()

    def send(rid, body: dict) -> None:
        # A future's done-callback runs where concurrent.futures calls it,
        # which swallows any exception it raises -- so a reply that fails to
        # write (e.g. a NaN `write` refuses) would otherwise leave that id
        # unanswered until onto's own timeout, rather than naming the fault.
        with lock:
            try:
                spot_protocol.write(out, rid, body)
            except Exception as exc:
                try:
                    spot_protocol.write(out, rid, _failed(exc))
                except Exception as exc2:
                    print(f"spot_worker: could not answer {rid!r}: {exc2}",
                          file=sys.stderr)

    def done(rid, fut: Future) -> None:
        exc = fut.exception()
        send(rid, _failed(exc) if exc is not None else fut.result())

    for rid, req in spot_protocol.read(inp):
        if req is None:
            send(rid, spot_protocol.reply(build=build(), error="BadRequest",
                                          detail="not a JSON object"))
        elif spot_protocol.is_ping(req):
            send(rid, spot_protocol.pong(build()))
        else:
            try:
                fut = pool.submit(answer, req)
            except BrokenProcessPool as exc:
                # The pool died between requests: this submit is the first
                # one to see it, synchronously, so answer it here and stop --
                # main() exits nonzero so onto restarts the service.
                send(rid, _failed(exc))
                wait(running)
                raise
            running.add(fut)
            fut.add_done_callback(lambda f, rid=rid: done(rid, f))
    wait(running)


def main() -> int:
    # stdout is the framing. Anything the engine prints would share it, so
    # fd 1 goes to stderr for this process and every one it starts.
    out = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    ctx = multiprocessing.get_context("spawn")
    try:
        with ProcessPoolExecutor(POOL, mp_context=ctx, initializer=warm) as pool:
            serve(sys.stdin, out, pool, render)
    except BrokenProcessPool:
        return 70
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
