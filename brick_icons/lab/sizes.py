"""What the corpus costs on disk, for the dashboard's footprint section.

Size on disk, never apparent size: the bakes are 303 MB of bytes and 615 MB
of blocks, because a 32px thumbnail is mostly block overhead. Two cells
measured different ways cannot be compared, so everything here is
`st_blocks * 512` -- the number `du` reports.
"""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path

from .. import db as corpus_db_module

# What each tile counts, in the order the dashboard draws them. `renders` is
# absent because it is summed from the database rather than walked -- see
# `_render_sizes`.
TILE_DIRS = (("out", "out"), ("bakes", "out/thumbs"), ("lab_cache", "out/lab"),
             ("git", ".git"))


def on_disk(entry: os.stat_result) -> int:
    """Blocks, not bytes. `st_blocks` is always 512-byte units regardless of
    the filesystem's own block size."""
    return entry.st_blocks * 512


def dir_size(path: Path) -> int:
    """Every file under `path`, or 0 if there is no such directory.

    `os.scandir` rather than `rglob`, because it reads type and stat from the
    directory entry and the corpus is hundreds of thousands of small files.
    """
    total = 0
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += on_disk(entry.stat(follow_symlinks=False))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _render_sizes(conn: sqlite3.Connection, root: Path) -> dict[str, int]:
    """Bytes of render per slot, counted over the rows the wall can reach.

    The database names every render's path, so this counts exactly the files
    a slot would serve rather than whatever its directory happens to hold --
    a half-fetched tree and an abandoned one both stop mattering.
    """
    sizes: dict[str, int] = {}
    for source, path in conn.execute("SELECT source, path FROM renders"):
        sizes.setdefault(source, 0)
        try:
            sizes[source] += on_disk(os.stat(root / path))
        except OSError:
            continue                     # a row whose file went away
    return sizes


def footprint(conn: sqlite3.Connection, root: Path | str = ".",
              ldraw_dir: Path | str | None = None) -> dict:
    """The tiles and the per-slot table the dashboard's footprint draws."""
    root = Path(root)
    renders = _render_sizes(conn, root)
    tiles = {name: dir_size(root / rel) for name, rel in TILE_DIRS}
    tiles["renders"] = sum(renders.values())
    tiles["library"] = dir_size(Path(ldraw_dir)) if ldraw_dir else 0
    db_path = root / corpus_db_module.DEFAULT_PATH
    try:
        tiles["corpus_db"] = on_disk(os.stat(db_path))
    except OSError:
        tiles["corpus_db"] = 0

    slots = []
    for source in corpus_db_module.SOURCES:
        bakes = dir_size(root / "out" / "thumbs" / source)
        made = renders.get(source, 0)
        if made or bakes:
            slots.append({"source": source, "renders": made, "bakes": bakes,
                          "total": made + bakes})
    slots.sort(key=lambda s: -s["total"])
    return {"tiles": tiles, "slots": slots,
            "as_of": dt.datetime.now(dt.timezone.utc).isoformat()}
