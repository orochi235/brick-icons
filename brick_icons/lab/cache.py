"""Rendered artifacts, keyed by the argv that produced them.

The key sorts the flags so that two commands that differ only in the order
their flags were typed hit one cache entry rather than two.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_ROOT = Path("out/lab")


def _canonical(argv: list[str]) -> str:
    parts, flags, i = [], [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            j = i + 1
            while j < len(argv) and not argv[j].startswith("--"):
                j += 1
            flags.append(" ".join(argv[i:j]))
            i = j
        else:
            parts.append(argv[i])
            i += 1
    return "\x00".join([*parts, *sorted(flags)])


def key(argv: list[str]) -> str:
    return hashlib.sha256(_canonical(argv).encode()).hexdigest()[:16]


def dir_for(argv: list[str], root: Path | str = DEFAULT_ROOT) -> Path:
    return Path(root) / key(argv)


def artifacts(directory: Path) -> list[dict]:
    """Every file in a cache dir, as name and byte size."""
    if not Path(directory).is_dir():
        return []
    return sorted(
        ({"name": p.name, "bytes": p.stat().st_size}
         for p in Path(directory).iterdir() if p.is_file()),
        key=lambda a: a["name"],
    )
