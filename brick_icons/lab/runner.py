"""Run one lab render.

The path is the CLI's: `build_parser().parse_args` for the argv, then
`_config_from_args`, then `process_one`. `process_one` returns nothing and
writes several files, so the render gets its own cache directory and the
artifacts are whatever appeared in it.

The render runs in a child process. Threads buy nothing here -- two `3941`
renders on threads take 16.3s against 10.7s run one after the other -- and
OCCT segfaults on some library parts, which on a thread takes the API server
down with it.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import shutil
import signal
import threading
import time
from pathlib import Path

from .. import cli
from . import cache

DEFAULT_WORKERS = 4
_CTX = mp.get_context("spawn")


def _worker_count() -> int:
    try:
        return max(1, int(os.environ.get("BRICK_LAB_WORKERS", DEFAULT_WORKERS)))
    except ValueError:
        return DEFAULT_WORKERS


_slots = threading.Semaphore(_worker_count())


def _command(argv: list[str]) -> str:
    return " ".join(["brick-icons", *argv])


def _death(code: int | None) -> str:
    if code is None:
        return "the render process died"
    if code < 0:
        try:
            name = signal.Signals(-code).name
        except ValueError:
            name = f"signal {-code}"
        return f"the render process died on {name}"
    return f"the render process exited {code}"


def _render_here(argv: list[str], out_dir: Path) -> dict:
    """The render itself, in whatever process is running it."""
    started = time.perf_counter()
    try:
        args, _ = cli.build_parser().parse_known_args(argv)
        cfg = cli._config_from_args(args)
        parts = cli._gather_parts(args)
        if not parts:
            raise ValueError("no part given")
        cli.process_one(cfg, parts[0], out_dir)
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}",
                "cancelled": False}
    return {"ok": True, "error": None, "cancelled": False}


def _child(argv: list[str], out_dir: str, conn) -> None:
    try:
        conn.send(_render_here(argv, Path(out_dir)))
    finally:
        conn.close()


def _received(conn) -> dict | None:
    """The child's answer, or None if the pipe closed without one."""
    try:
        return conn.recv()
    except EOFError:
        return None


def _reaped(proc) -> int | None:
    proc.join(5)
    return proc.exitcode


def _collect(proc, conn, cancel: threading.Event | None) -> dict:
    """What the child sent, or why nothing came."""
    while True:
        if conn.poll(0.1):
            got = _received(conn)
            if got is not None:
                return got
            return {"ok": False, "error": _death(_reaped(proc)),
                    "cancelled": False}
        if cancel is not None and cancel.is_set():
            proc.terminate()
            proc.join(5)
            return {"ok": False, "error": "cancelled", "cancelled": True}
        if not proc.is_alive():
            # It may have sent as it exited, so the pipe outranks the exit code.
            if conn.poll(0):
                got = _received(conn)
                if got is not None:
                    return got
            return {"ok": False, "error": _death(_reaped(proc)),
                    "cancelled": False}


def render(argv: list[str], root: Path | str = cache.DEFAULT_ROOT,
           force: bool = False,
           cancel: threading.Event | None = None) -> dict:
    out_dir = cache.dir_for(argv, root=root)
    existing = cache.artifacts(out_dir)
    if existing and not force:
        return {"ok": True, "cached": True, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": existing, "seconds": 0.0, "pid": None,
                "error": None}
    if force and out_dir.exists():
        shutil.rmtree(out_dir)

    parser = cli.build_parser()
    parser.exit_on_error = False

    def failed(message: str) -> dict:
        return {"ok": False, "cached": False, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": [], "seconds": 0.0, "pid": None,
                "error": message}

    # `parse_args` on an unknown flag calls `parser.error`, which raises
    # SystemExit(2) -- whose str() is "2", losing the message the caller needs.
    # Parsing in this process keeps a typo cheap: no worker is spawned for it.
    try:
        args, extra = parser.parse_known_args(argv)
    except (argparse.ArgumentError, SystemExit) as e:
        return failed(f"bad arguments: {e}")
    if extra:
        return failed(f"unrecognized arguments: {' '.join(extra)}")

    started = time.perf_counter()
    with _slots:
        receive, send = _CTX.Pipe(duplex=False)
        proc = _CTX.Process(target=_child, args=(argv, str(out_dir), send),
                            daemon=True)
        proc.start()
        try:
            outcome = _collect(proc, receive, cancel)
        finally:
            send.close()
            receive.close()
            if proc.is_alive():
                proc.terminate()
            proc.join()

    return {"ok": outcome["ok"], "cached": False, "argv": argv,
            "command": _command(argv), "key": cache.key(argv),
            "artifacts": cache.artifacts(out_dir),
            "seconds": time.perf_counter() - started, "pid": proc.pid,
            "cancelled": outcome["cancelled"], "error": outcome["error"]}
