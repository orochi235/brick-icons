"""OCCT-backed hidden-line removal. The only module that imports OCP."""
from __future__ import annotations

try:
    import OCP  # noqa: F401
except ImportError as e:                      # pragma: no cover
    raise ImportError(
        "--engine occt needs the OCCT extra: pip install -e '.[occt]'"
    ) from e


def visible_segments(out, right, up, fwd, render_px, cull=True):
    raise NotImplementedError("OCCT engine lands in Task 6")
