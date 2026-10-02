"""How far one render has got, as a fraction of itself, for whoever is watching.

The render reports nothing directly. Each `timing.phase` that opens moves the
bar to where that phase starts (`STARTS`), and a phase with a loop of known
length reports inside it with `step`, which spreads across the band up to the
next start. Only a watcher's sink knows what the fraction is a fraction OF --
one part of a batch, a lab pane -- so this module never prints.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from . import timing

if TYPE_CHECKING:
    from .config import Config

#: Where each phase opens, as a share of a render of five seconds or more, by
#: engine, for a drawing with fills. Phase paths are relative to the render.
#: Measured by scripts/calibrate-progress.py, which also scores how far the
#: bar strays. Without fills the render ends where `fill` would start.
STARTS: dict[str, dict[str, float]] = {
    "occt": {"geometry": 0.0, "geometry/import": 0.009,
             "geometry/engine": 0.071, "geometry/engine/faces": 0.125,
             "geometry/dedupe": 0.390, "studs": 0.395, "fill": 0.396},
    "naive": {"geometry": 0.0, "geometry/engine": 0.026,
              "geometry/dedupe": 0.402, "studs": 0.411, "fill": 0.411},
}

Sink = Callable[[str, float], None]

_on: "_Watch | None" = None


class _Watch:
    def __init__(self, sink: Sink, engine: str, fills: bool) -> None:
        self.sink = sink
        self.starts = plan(engine, fills)
        self.edges = sorted(set(self.starts.values()) | {1.0})
        self.band = (0.0, self.edges[1] if len(self.edges) > 1 else 1.0)
        self.fraction = 0.0
        self.label = ""
        self.sent: tuple[str, int] | None = None

    def opened(self, path: str) -> None:
        path = _relative(path)
        if not path:
            return
        self.label = path
        if path in self.starts:
            lo = self.starts[path]
            self.band = (lo, next((e for e in self.edges if e > lo), 1.0))
            self._move(lo)
        self._send()

    def step(self, done: int, total: int) -> None:
        if total > 0:
            # the phase still open, not the last one opened: a step runs
            # after a child phase has closed
            self.label = _relative(timing.current()) or self.label
            lo, hi = self.band
            self._move(lo + (hi - lo) * min(done, total) / total)
            self._send()

    def _move(self, f: float) -> None:
        # parallel and repeated phases may reopen an earlier band; never back
        self.fraction = max(self.fraction, min(f, 1.0))

    def _send(self) -> None:
        # a whole percent or a new label, so a tight loop costs nothing
        now = (self.label, int(self.fraction * 100))
        if now != self.sent:
            self.sent = now
            self.sink(self.label, self.fraction)


def _relative(path: str) -> str:
    """A phase path below the render, which a census wraps in `render`."""
    if path == "render" or path.startswith("render/"):
        return path.partition("/")[2]
    return path


def plan(engine: str, fills: bool) -> dict[str, float]:
    """Where each phase starts in a render of `engine`, with or without fills."""
    starts = dict(STARTS.get(engine, {}))
    end = starts.pop("fill", None)
    if fills or not end:
        return STARTS.get(engine, {})
    return {k: v / end for k, v in starts.items()}


def watch(sink: Sink | None, cfg: Config | None = None) -> None:
    """Send `(phase, fraction)` to `sink` for renders under `cfg` from now
    on, or stop with None."""
    global _on
    _on = _Watch(sink, cfg.engine if cfg else "",
                 cfg.draws_fills if cfg else True) if sink else None
    timing.listen(_on.opened if _on else None)


def step(done: int, total: int) -> None:
    """`done` of `total` through the innermost phase with a band. Free when
    nobody is watching."""
    if _on is not None:
        _on.step(done, total)
