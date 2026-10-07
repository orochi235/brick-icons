"""Clocks that stop while onto has the job stopped.

`onto run --pausable` lets a test suite on the node SIGSTOP a pool's items and
SIGCONT them when it ends. Wall time keeps passing meanwhile, so a part's cap
must count only the time it was not stopped: onto publishes the job's
cumulative stopped seconds in the file named by $ONTO_PAUSED, and a deadline
here moves out by however much that grew since the part began.
"""
from __future__ import annotations

import os
import time
from pathlib import Path


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

    def left(self) -> float:
        """Seconds remaining; zero or less only once the cap has really run."""
        now = paused_seconds()
        if now > self.base:
            self.at += now - self.base
            self.base = now
        return self.at - time.monotonic()


class Stopwatch:
    """Elapsed seconds with onto's stopped time taken out."""

    def __init__(self):
        self.t0 = time.time()
        self.base = paused_seconds()

    def secs(self) -> float:
        return max(0.0, time.time() - self.t0 - (paused_seconds() - self.base))

