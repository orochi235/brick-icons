"""Render LEGO parts from LDraw into bin-label bitmaps and SVGs."""
from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

__version__ = "0.1.0"


@cache
def build() -> str:
    """The engine revision that drew something, as `<count>.<short sha>`.

    Derived from git rather than stored: a counter kept in a file conflicts
    on every branch and cannot be recomputed for a commit that already
    exists, while `rev-list --count` is exact for any revision after the
    fact. Suffixed `+` when the tree is dirty -- an uncommitted engine is
    not the commit it sits on.
    """
    root = Path(__file__).resolve().parent.parent
    try:
        def git(*a):
            return subprocess.run(("git", "-C", str(root)) + a, check=True,
                                  capture_output=True, text=True).stdout.strip()
        n, sha = git("rev-list", "--count", "HEAD"), git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain", "--", "brick_icons")
        return f"{n}.{sha}" + ("+" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
