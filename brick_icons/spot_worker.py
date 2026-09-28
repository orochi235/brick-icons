"""The spot render worker: one warm process on the fleet that draws a part
the moment the lab asks.

onto runs it as a service through `scripts/spot-worker.sh` (DEVELOPING.md,
"Spot rendering"). Each pool process imports the engine once, then draws
every request it is handed in a forked child, through the CLI's own path and
under the batch per-part cap, so a redraw pays for the render and not for
Python starting up.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

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
