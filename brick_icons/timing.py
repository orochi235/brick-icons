"""Phase timings for one render, collected where the work happens.

`measurements.secs` says a part was slow; the phases say which half of the
engine was slow, which is the difference between a census row you can act on
and one you have to reproduce by hand. The accumulator is process-global and
explicitly reset, because the render path threads no context object and one
`with` at each site is the whole cost.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps

_phases: dict[str, float] = {}
_stack: list[float] = []


def reset() -> None:
    _phases.clear()
    _stack.clear()


def phases() -> dict[str, float]:
    return {k: round(v, 3) for k, v in _phases.items()}


@contextmanager
def phase(name: str):
    """Time this block, EXCLUDING any nested phase. Decoration runs inside the
    geometry phase, so without this the two would double-count and a stacked
    chart of them would not sum to the render."""
    t = time.perf_counter()
    _stack.append(0.0)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - t
        nested = _stack.pop()
        _phases[name] = _phases.get(name, 0.0) + elapsed - nested
        if _stack:
            _stack[-1] += elapsed


def timed(name: str):
    """Decorator form, for a phase that is exactly one function."""
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **k):
            with phase(name):
                return fn(*a, **k)
        return wrap
    return deco
