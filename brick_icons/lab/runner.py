"""Run one lab render.

The path is the CLI's: `build_parser().parse_args` for the argv, then
`_config_from_args`, then `process_one`. `process_one` returns nothing and
writes several files, so the render gets its own cache directory and the
artifacts are whatever appeared in it.
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from .. import cli
from . import cache


def _command(argv: list[str]) -> str:
    return " ".join(["brick-icons", *argv])


def render(argv: list[str], root: Path | str = cache.DEFAULT_ROOT,
           force: bool = False) -> dict:
    out_dir = cache.dir_for(argv, root=root)
    existing = cache.artifacts(out_dir)
    if existing and not force:
        return {"ok": True, "cached": True, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": existing, "seconds": 0.0, "error": None}
    if force and out_dir.exists():
        shutil.rmtree(out_dir)

    parser = cli.build_parser()
    parser.exit_on_error = False

    def failed(message: str) -> dict:
        return {"ok": False, "cached": False, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": [], "seconds": 0.0, "error": message}

    # `parse_args` on an unknown flag calls `parser.error`, which raises
    # SystemExit(2) -- whose str() is "2", losing the message the caller needs.
    try:
        args, extra = parser.parse_known_args(argv)
    except (argparse.ArgumentError, SystemExit) as e:
        return failed(f"bad arguments: {e}")
    if extra:
        return failed(f"unrecognized arguments: {' '.join(extra)}")

    started = time.perf_counter()
    try:
        cfg = cli._config_from_args(args)
        parts = cli._gather_parts(args)
        if not parts:
            raise ValueError("no part given")
        cli.process_one(cfg, parts[0], out_dir)
    except Exception as e:                          # noqa: BLE001
        return {"ok": False, "cached": False, "argv": argv,
                "command": _command(argv), "key": cache.key(argv),
                "artifacts": cache.artifacts(out_dir),
                "seconds": time.perf_counter() - started,
                "error": f"{type(e).__name__}: {e}"}

    return {"ok": True, "cached": False, "argv": argv,
            "command": _command(argv), "key": cache.key(argv),
            "artifacts": cache.artifacts(out_dir),
            "seconds": time.perf_counter() - started, "error": None}
