"""Phase timings and event counts for one render, collected where the work
happens.

`measurements.secs` says a part was slow; the phases say which part of the
engine was slow, which is the difference between a census row you can act on
and one you have to reproduce by hand. The accumulator is process-global and
explicitly reset, because the render path threads no context object and one
`with` at each site is the whole cost.

A phase names its parent: opening `geometry` inside `render` records
`render/geometry`, and a phase's time is INCLUSIVE of everything under it.
That is what lets a new seam be added at any depth without redefining the
band above it -- a level's own leftover is `parent - sum(children)`, worked
out once when the tree is read rather than at every `with`.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps

SEP = "/"

_phases: dict[str, float] = {}
_counts: dict[str, int] = {}
_stack: list[str] = []


def reset() -> None:
    _phases.clear()
    _counts.clear()
    _stack.clear()


def phases() -> dict[str, float]:
    return {k: round(v, 3) for k, v in _phases.items()}


def count(name: str, n: int = 1) -> None:
    """Record that something happened, for a render fact that is not a time.

    A phase cannot carry one: a kernel call the engine had to work around
    still took seconds, so its timing says nothing about whether it ran.
    """
    _counts[name] = _counts.get(name, 0) + n


def counts() -> dict[str, int]:
    return dict(_counts)


@contextmanager
def phase(name: str):
    """Time this block under whatever phase is already open.

    Inclusive: a parent keeps the time its children spent. Two blocks opened
    with the same path accumulate into one entry, so a phase entered once per
    subpart reports the total rather than the last one.
    """
    if SEP in name:
        raise ValueError(f"a phase name cannot contain {SEP!r}: {name!r}")
    _stack.append(name)
    path = SEP.join(_stack)
    t = time.perf_counter()
    try:
        yield
    finally:
        _phases[path] = _phases.get(path, 0.0) + time.perf_counter() - t
        _stack.pop()


def timed(name: str):
    """Decorator form, for a phase that is exactly one function."""
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **k):
            with phase(name):
                return fn(*a, **k)
        return wrap
    return deco
