import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def ldraw_dir():
    """Path to the vendored LDraw parts library; skips if not present."""
    path = Path(__file__).resolve().parent.parent / "vendor" / "ldraw"
    if not path.exists():
        pytest.skip("vendor/ldraw not present")
    return path


@pytest.fixture
def concurrently():
    """`run(n, call)`: `call()` from `n` threads released together, so every
    one of them asks while the first is still computing."""
    def run(n, call):
        gate = threading.Barrier(n)
        out = [None] * n

        def one(i):
            gate.wait()
            out[i] = call()
        threads = [threading.Thread(target=one, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return out
    return run


@pytest.fixture
def slow_counted(monkeypatch):
    """`slow_counted(module, name)` replaces `module.name` with a copy that
    takes half a second longer and records each call in the list returned."""
    def patch(module, name):
        real = getattr(module, name)
        calls = []

        def slow(*args, **kwargs):
            calls.append(1)
            time.sleep(0.5)
            return real(*args, **kwargs)
        monkeypatch.setattr(module, name, slow)
        return calls
    return patch


@pytest.fixture
def gradient_rgba():
    """256x64 horizontal black->white gradient, fully opaque, as RGBA."""
    row = np.linspace(0, 255, 256, dtype=np.uint8)
    arr = np.tile(row, (64, 1))
    rgb = np.dstack([arr, arr, arr])
    alpha = np.full((64, 256), 255, dtype=np.uint8)
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


@pytest.fixture
def half_transparent_rgba():
    """64x64: left half opaque mid-gray, right half fully transparent."""
    arr = np.zeros((64, 64, 4), dtype=np.uint8)
    arr[:, :32, :3] = 96
    arr[:, :32, 3] = 255
    return Image.fromarray(arr, "RGBA")


@pytest.fixture
def disc_rgba():
    """96x96 opaque gray filled circle on transparent bg (a curvy silhouette)."""
    yy, xx = np.mgrid[0:96, 0:96]
    mask = (xx - 48) ** 2 + (yy - 48) ** 2 <= 40 ** 2
    arr = np.zeros((96, 96, 4), dtype=np.uint8)
    arr[mask, :3] = 110
    arr[mask, 3] = 255
    return Image.fromarray(arr, "RGBA")


class StubSpot:
    """The spot worker as the lab sees it, answering from a script instead
    of through onto: `reply` is what a draw returns, `down` or `error` (with
    `error_kind`) make it raise instead, and `gate` holds a draw until set."""

    def __init__(self, reply=None, *, down=None, error=None,
                 error_kind="SpotError", status=None, want="9.ccccccc",
                 gate=None):
        self.reply, self.down, self.error = reply, down, error
        self.error_kind, self.want, self.gate = error_kind, want, gate
        self._status = status or {"state": "up", "build": want, "want": want,
                                  "detail": None}
        self.calls = []

    def expected(self):
        return ("c" * 40, self.want)

    def draw(self, request, commit):
        from brick_icons.lab import spot
        self.calls.append((request, commit))
        if self.gate is not None:
            self.gate.wait(5)
        if self.down:
            raise spot.SpotDown(self.down)
        if self.error:
            raise spot.SpotError(self.error, self.error_kind)
        return self.reply

    def status(self):
        return self._status


@pytest.fixture
def stub_spot():
    """The `StubSpot` class, to build one per test."""
    return StubSpot
