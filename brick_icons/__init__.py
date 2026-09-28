"""Render LEGO parts from LDraw into bin-label bitmaps and SVGs."""
from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

__version__ = "0.1.0"


_ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(_ROOT)) + args, check=True,
                          capture_output=True, text=True).stdout.strip()


def build_of(rev: str) -> str:
    """`build()`'s `<count>.<short sha>` for any revision, or "unknown".

    Never suffixed `+`: only a working tree can be dirty, and this names a
    commit. The lab asks it of origin/main, the build it tells the spot worker
    to draw at.
    """
    try:
        return f"{_git('rev-list', '--count', rev)}.{_git('rev-parse', '--short', rev)}"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def commit_of(rev: str) -> str | None:
    """The full sha `rev` names, or None where git cannot say."""
    try:
        return _git("rev-parse", "--verify", f"{rev}^{{commit}}")
    except (OSError, subprocess.CalledProcessError):
        return None


@cache
def build() -> str:
    """The engine revision that drew something, as `<count>.<short sha>`.

    Derived from git rather than stored: a counter kept in a file conflicts
    on every branch and cannot be recomputed for a commit that already
    exists, while `rev-list --count` is exact for any revision after the
    fact. Suffixed `+` when the tree is dirty -- an uncommitted engine is
    not the commit it sits on.
    """
    made = build_of("HEAD")
    if made == "unknown":
        return made
    try:
        dirty = _git("status", "--porcelain", "--", "brick_icons")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return made + ("+" if dirty else "")
