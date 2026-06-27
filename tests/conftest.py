import numpy as np
import pytest
from PIL import Image


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
