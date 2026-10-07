"""Clocks that stop while onto has the job stopped.

`onto run --pausable` lets a test suite on the node SIGSTOP a pool's items and
SIGCONT them when it ends. Wall time keeps passing meanwhile, so a part's cap
must count only the time it was not stopped: onto publishes the job's
cumulative stopped seconds in the file named by $ONTO_PAUSED, and a deadline
here moves out by however much that grew since the part began.
"""
from __future__ import annotations

import ctypes
import os
import signal
import time
from pathlib import Path

# onto continues the job and only then writes the new total, so an expiry seen
# in that window looks again once before it stands.
_SETTLE = 1.0

# How often a minder checks whether the batch process has been stopped.
_FOLLOW = 0.25

# proc_pidinfo(PROC_PIDTBSDINFO): struct proc_bsdinfo is 136 bytes, and
# pbi_status, a uint32 after pbi_flags, reads SSTOP for a stopped process.
_PIDTBSDINFO = 3
_BSDINFO_SIZE = 136
_SSTOP = 4
_libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)


def paused_seconds() -> int:
    """Seconds onto has held this job stopped, or 0 outside onto."""
    path = os.environ.get("ONTO_PAUSED")
    if not path:
        return 0
    try:
        return max(0, int(Path(path).read_text().strip() or 0))
    except (OSError, ValueError):
        return 0


class Deadline:
    """`secs` from now, not counting time onto spends with the job stopped."""

    def __init__(self, secs: float):
        self.secs = secs
        self.at = time.monotonic() + secs
        self.base = paused_seconds()

    def _catch_up(self) -> float:
        now = paused_seconds()
        if now > self.base:
            self.at += now - self.base
            self.base = now
        return self.at - time.monotonic()

    def left(self) -> float:
        """Seconds remaining; zero or less only once the cap has really run."""
        left = self._catch_up()
        if left <= 0 and os.environ.get("ONTO_PAUSED"):
            time.sleep(_SETTLE)
            left = self._catch_up()
        return left


class Stopwatch:
    """Elapsed seconds with onto's stopped time taken out."""

    def __init__(self):
        self.t0 = time.time()
        self.base = paused_seconds()

    def secs(self) -> float:
        return max(0.0, time.time() - self.t0 - (paused_seconds() - self.base))


def _stopped(pid: int) -> bool | None:
    """Whether `pid` is stopped, or None once it is gone."""
    buf = ctypes.create_string_buffer(_BSDINFO_SIZE)
    got = _libc.proc_pidinfo(ctypes.c_int(pid), ctypes.c_int(_PIDTBSDINFO),
                             ctypes.c_uint64(0), buf, ctypes.c_int(_BSDINFO_SIZE))
    if got != _BSDINFO_SIZE:
        return None
    return int.from_bytes(buf.raw[4:8], "little") == _SSTOP


def follow_stops(pgid: int) -> int:
    """Fork a minder that stops and continues process group `pgid` along with
    this process, and return its pid; the caller kills it when done.

    onto stops an item's own process group. A render isolated in a group of
    its own is outside it and would keep its core through the pause, so the
    one thing a pause is for would not happen. The minder takes a third group:
    in the item's it would be stopped too, in the render's it would stop
    itself.
    """
    parent = os.getpid()
    pid = os.fork()
    if pid:
        return pid
    held = False
    try:
        os.setpgid(0, 0)
        while os.getppid() == parent:
            stopped = _stopped(parent)
            if stopped is None:
                break
            if stopped != held:
                os.killpg(pgid, signal.SIGSTOP if stopped else signal.SIGCONT)
                held = stopped
            time.sleep(_FOLLOW)
    except BaseException:
        pass
    finally:
        if held:
            try:
                os.killpg(pgid, signal.SIGCONT)
            except OSError:
                pass
        os._exit(0)
