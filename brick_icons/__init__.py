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


def _git_or_none(*args: str) -> str | None:
    try:
        return _git(*args)
    except (OSError, subprocess.CalledProcessError):
        return None


def build_of(rev: str) -> str:
    """`build()`'s `<count>.<short sha>` for any revision, or "unknown".

    Never suffixed `+`: only a working tree can be dirty, and this names a
    commit. The lab asks it of origin/main, the build it tells the spot worker
    to draw at. "unknown" in a shallow clone too: `rev-list --count` undercounts
    there, so the same commit would otherwise get two different build strings
    depending on which tree -- the lab's or a fleet node's -- named it.
    """
    if _git_or_none("rev-parse", "--is-shallow-repository") == "true":
        return "unknown"
    count = _git_or_none("rev-list", "--count", rev)
    sha = _git_or_none("rev-parse", "--short", rev)
    if count is None or sha is None:
        return "unknown"
    return f"{count}.{sha}"


def commit_of(rev: str) -> str | None:
    """The full sha `rev` names, or None where git cannot say."""
    return _git_or_none("rev-parse", "--verify", f"{rev}^{{commit}}")


@cache
def build() -> str:
    """The engine revision that drew something, as `<count>.<short sha>`.

    Derived from git rather than stored: a counter kept in a file conflicts
    on every branch and cannot be recomputed for a commit that already
    exists. Suffixed `+` when the tree is dirty -- an uncommitted engine is
    not the commit it sits on.
    """
    made = build_of("HEAD")
    if made == "unknown":
        return made
    dirty = _git_or_none("status", "--porcelain", "--", "brick_icons")
    if dirty is None:
        return "unknown"
    return made + ("+" if dirty else "")
