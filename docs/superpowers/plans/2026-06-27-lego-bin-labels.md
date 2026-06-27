# lego-bin-labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python CLI that renders LEGO parts from LDraw via LDView and emits either 1-bit dithered bitmaps sized for a Brother P-touch label or higher-resolution grayscale images for the driver to dither.

**Architecture:** Pure, unit-testable image-processing core (`process.py`) plus a thin LDView subprocess wrapper (`render.py`), a config loader (`config.py`), and a CLI (`cli.py`) that wires part inputs to label outputs. Renders are produced transparent and flattened onto white in Pillow for full control. LDView is x86_64-only and runs under Rosetta on Apple Silicon.

**Tech Stack:** Python 3.11+ (stdlib `tomllib`, `argparse`, `subprocess`), Pillow, NumPy. LDView 4.2.1 (SourceForge dmg). LDraw `complete.zip`. macOS (`arch -x86_64`, `hdiutil`).

---

## File Structure

```
lego-bin-labels/
  pyproject.toml                 # package metadata + deps (pillow, numpy)
  labels.toml                    # default config values
  README.md
  .gitignore                     # already present; add vendor/
  scripts/
    setup-ldview.sh              # download+install LDView.app and LDraw lib into vendor/
  lego_bin_labels/
    __init__.py
    config.py                    # load labels.toml + merge CLI overrides -> Config
    render.py                    # resolve part, build LDView argv, run snapshot
    process.py                   # flatten/grayscale/levels/fit + 4 dither algos
    cli.py                       # argparse, modes (gray/mono/both), batch, debug-dir
  tests/
    conftest.py                  # shared fixtures (synthetic gradient image)
    test_config.py
    test_process.py
    test_render.py               # argv builder (unit) + live render (skip if no LDView)
    test_cli.py                  # mode/batch wiring with render mocked
  vendor/                        # gitignored: LDView.app, ldraw/  (from setup script)
```

**Responsibilities:**
- `process.py` — pure functions, no I/O beyond PIL images; fully unit-tested.
- `render.py` — `build_argv()` is pure (unit-tested); `render_part()` shells out.
- `config.py` — resolves defaults + toml + overrides + label-mm→pixels.
- `cli.py` — orchestration only; calls config → render → process → write.

---

## Task 1: Project scaffold and dependencies

**Files:**
- Create: `pyproject.toml`, `lego_bin_labels/__init__.py`, `tests/conftest.py`
- Modify: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "lego-bin-labels"
version = "0.1.0"
description = "Render LEGO parts from LDraw into monochrome/grayscale bin-label bitmaps"
requires-python = ">=3.11"
dependencies = ["pillow>=10", "numpy>=1.26"]

[project.scripts]
lego-bin-labels = "lego_bin_labels.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["lego_bin_labels*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create the package init**

`lego_bin_labels/__init__.py`:

```python
"""Render LEGO parts from LDraw into bin-label bitmaps."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Add `vendor/` to `.gitignore`**

Append to `.gitignore` (it already contains `out/` and `debug/`):

```
vendor/
.venv/
.pytest_cache/
```

- [ ] **Step 4: Create the test venv and install**

Run:

```bash
cd ~/src/lego-bin-labels
python3 -m venv .venv
.venv/bin/pip install -q -e '.[ ]' 2>/dev/null || .venv/bin/pip install -q -e .
.venv/bin/pip install -q pytest
.venv/bin/python -c "import PIL, numpy; print('deps ok')"
```

Expected: `deps ok`

- [ ] **Step 5: Create `tests/conftest.py` with a shared synthetic fixture**

```python
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
    """64x64 image: left half opaque black, right half fully transparent."""
    arr = np.zeros((64, 64, 4), dtype=np.uint8)
    arr[:, :32, 3] = 255   # left half opaque black
    # right half stays (0,0,0,0) transparent
    return Image.fromarray(arr, "RGBA")
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml lego_bin_labels/__init__.py tests/conftest.py .gitignore
git commit -m "chore: scaffold lego-bin-labels package and test deps"
```

---

## Task 2: LDView + LDraw setup script

**Files:**
- Create: `scripts/setup-ldview.sh`

This is I/O-heavy (downloads ~140 MB); verified by running it, not by unit test. It must be idempotent.

- [ ] **Step 1: Write `scripts/setup-ldview.sh`**

```bash
#!/usr/bin/env bash
# Install LDView.app and the LDraw parts library into ./vendor (idempotent).
set -euo pipefail
cd "$(dirname "$0")/.."
VENDOR="$PWD/vendor"
mkdir -p "$VENDOR"

DMG_URL="https://downloads.sourceforge.net/project/ldview/01.%20LDView/LDView%204.2/LDView_4.2.1_Universal.dmg?viasf=1"
LDRAW_URL="https://library.ldraw.org/library/updates/complete.zip"

# --- LDView.app ---
if [ ! -x "$VENDOR/LDView.app/Contents/MacOS/LDView" ]; then
  echo "Downloading LDView dmg..."
  curl -sL -o "$VENDOR/LDView.dmg" "$DMG_URL"
  MNT="$VENDOR/.ldview-mnt"
  mkdir -p "$MNT"
  hdiutil attach "$VENDOR/LDView.dmg" -nobrowse -noverify -mountpoint "$MNT" >/dev/null
  rm -rf "$VENDOR/LDView.app"
  cp -R "$MNT/LDView.app" "$VENDOR/LDView.app"
  hdiutil detach "$MNT" >/dev/null
  rm -f "$VENDOR/LDView.dmg"
  # Strip quarantine so Gatekeeper does not pop a dialog on first run.
  xattr -dr com.apple.quarantine "$VENDOR/LDView.app" 2>/dev/null || true
  echo "LDView installed."
else
  echo "LDView already present."
fi

# --- LDraw library ---
if [ ! -f "$VENDOR/ldraw/parts/3001.dat" ]; then
  echo "Downloading LDraw complete.zip (~140 MB)..."
  curl -sL -o "$VENDOR/complete.zip" "$LDRAW_URL"
  echo "Unzipping..."
  rm -rf "$VENDOR/ldraw"
  unzip -q -o "$VENDOR/complete.zip" -d "$VENDOR"   # creates $VENDOR/ldraw
  rm -f "$VENDOR/complete.zip"
  echo "LDraw library installed."
else
  echo "LDraw library already present."
fi

echo "Verifying..."
test -x "$VENDOR/LDView.app/Contents/MacOS/LDView"
test -f "$VENDOR/ldraw/parts/3001.dat"
echo "Setup OK: $VENDOR/LDView.app and $VENDOR/ldraw"
```

- [ ] **Step 2: Make it executable and run it**

Run:

```bash
chmod +x scripts/setup-ldview.sh
./scripts/setup-ldview.sh
```

Expected final line: `Setup OK: .../vendor/LDView.app and .../vendor/ldraw`

- [ ] **Step 3: Verify a live render works (manual smoke check)**

Run:

```bash
arch -x86_64 vendor/LDView.app/Contents/MacOS/LDView \
  vendor/ldraw/parts/3001.dat -LDrawDir="$PWD/vendor/ldraw" \
  -SaveSnapshot="$PWD/vendor/_smoke.png" -SaveWidth=256 -SaveHeight=256 \
  -AutoCrop=1 -SaveAlpha=1 ; file vendor/_smoke.png ; rm -f vendor/_smoke.png
```

Expected: `vendor/_smoke.png: PNG image data, ... RGBA ...`

- [ ] **Step 4: Commit (script only; vendor/ is gitignored)**

```bash
git add scripts/setup-ldview.sh
git commit -m "feat: add LDView + LDraw setup script"
```

---

## Task 3: Config loader

**Files:**
- Create: `lego_bin_labels/config.py`, `labels.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from pathlib import Path
from lego_bin_labels.config import Config, load_config


def test_defaults_when_no_toml_no_overrides():
    cfg = load_config(toml_path=None, overrides=None, root="/proj")
    assert cfg.dpi == 180
    assert cfg.mode == "both"
    assert cfg.dither == "atkinson"
    assert cfg.width == 256 and cfg.height == 170
    # paths resolved relative to root
    assert cfg.ldraw_dir == Path("/proj/vendor/ldraw")
    assert cfg.ldview == Path("/proj/vendor/LDView.app/Contents/MacOS/LDView")


def test_overrides_win_and_none_is_ignored():
    cfg = load_config(overrides={"dpi": 360, "dither": "floyd", "width": None}, root="/p")
    assert cfg.dpi == 360
    assert cfg.dither == "floyd"
    assert cfg.width == 256  # None override ignored, default kept


def test_label_mm_computes_pixels_from_dpi():
    # 24mm x 12mm at 180 dpi -> round(mm/25.4*dpi)
    cfg = load_config(overrides={"label_mm": (24.0, 12.0), "dpi": 180}, root="/p")
    assert cfg.width == round(24.0 / 25.4 * 180)   # 170
    assert cfg.height == round(12.0 / 25.4 * 180)  # 85


def test_toml_values_used(tmp_path):
    toml = tmp_path / "labels.toml"
    toml.write_text('dpi = 360\ndither = "ordered"\n')
    cfg = load_config(toml_path=str(toml), root="/p")
    assert cfg.dpi == 360 and cfg.dither == "ordered"


def test_render_param_defaults_and_overrides():
    cfg = load_config(root="/p")
    assert cfg.angle == "iso" and cfg.shading == "normal" and cfg.scale == 1.0
    cfg2 = load_config(overrides={"angle": "top", "shading": "flat", "scale": 0.8}, root="/p")
    assert cfg2.angle == "top" and cfg2.shading == "flat" and cfg2.scale == 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lego_bin_labels.config'`

- [ ] **Step 3: Write `lego_bin_labels/config.py`**

```python
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

MM_PER_INCH = 25.4

DEFAULTS = {
    "ldview": "vendor/LDView.app/Contents/MacOS/LDView",
    "ldraw_dir": "vendor/ldraw",
    "dpi": 180,
    "label_mm": None,     # (width_mm, height_mm) or None
    "width": 256,         # px; ignored if label_mm given
    "height": 170,        # px; ignored if label_mm given
    "margin": 6,          # px padding inside the label
    "render_px": 1024,    # LDView supersample square size
    "style": "shaded",    # "shaded" | "lineart"
    "angle": "iso",       # preset name or "LAT,LONG"
    "shading": "normal",  # "normal" | "flat" | "subdued"
    "scale": 1.0,         # fraction of label view area the part fills (0-1)
    "mode": "both",       # "gray" | "mono" | "both"
    "dither": "atkinson", # "threshold" | "floyd" | "ordered" | "atkinson"
    "threshold": 128,
    "gamma": 1.0,
    "levels": None,       # (black_in, white_in) 0-255 or None
}


@dataclass(frozen=True)
class Config:
    ldview: Path
    ldraw_dir: Path
    dpi: int
    width: int
    height: int
    margin: int
    render_px: int
    style: str
    angle: str
    shading: str
    scale: float
    mode: str
    dither: str
    threshold: int
    gamma: float
    levels: tuple | None


def load_config(toml_path: str | None = None,
                overrides: dict | None = None,
                root: str | Path = ".") -> Config:
    data = dict(DEFAULTS)
    if toml_path and Path(toml_path).exists():
        with open(toml_path, "rb") as f:
            data.update(tomllib.load(f))
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    root = Path(root)
    label_mm = data.get("label_mm")
    if label_mm:
        w_mm, h_mm = label_mm
        data["width"] = round(w_mm / MM_PER_INCH * data["dpi"])
        data["height"] = round(h_mm / MM_PER_INCH * data["dpi"])

    return Config(
        ldview=(root / data["ldview"]),
        ldraw_dir=(root / data["ldraw_dir"]),
        dpi=int(data["dpi"]),
        width=int(data["width"]),
        height=int(data["height"]),
        margin=int(data["margin"]),
        render_px=int(data["render_px"]),
        style=str(data["style"]),
        angle=str(data["angle"]),
        shading=str(data["shading"]),
        scale=float(data["scale"]),
        mode=str(data["mode"]),
        dither=str(data["dither"]),
        threshold=int(data["threshold"]),
        gamma=float(data["gamma"]),
        levels=tuple(data["levels"]) if data["levels"] else None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: Create `labels.toml` with documented defaults**

```toml
# Default configuration for lego-bin-labels. CLI flags override these.
dpi = 180             # P-touch printers are typically 180 or 360 dpi
margin = 6            # px of whitespace inside each label
render_px = 1024      # LDView supersample size before downscaling
style = "shaded"      # "shaded" (3D) or "lineart" (white surfaces, black edges)
angle = "iso"         # iso | front | back | left | right | top | bottom | "LAT,LONG"
shading = "normal"    # "normal" | "flat" | "subdued"
scale = 1.0           # fraction of the label view area the part fills (0-1)
mode = "both"         # "gray" | "mono" | "both"
dither = "atkinson"   # "threshold" | "floyd" | "ordered" | "atkinson"
threshold = 128
gamma = 1.0
# label_mm = [24.0, 12.0]   # uncomment to size by physical tape instead of px
```

- [ ] **Step 6: Commit**

```bash
git add lego_bin_labels/config.py labels.toml tests/test_config.py
git commit -m "feat: add config loader with mm->px sizing"
```

---

## Task 4: Image normalization (flatten, grayscale, levels, fit)

**Files:**
- Create: `lego_bin_labels/process.py`
- Test: `tests/test_process.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_process.py`:

```python
import numpy as np
from PIL import Image
from lego_bin_labels import process


def test_to_grayscale_flattens_transparency_onto_white(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    assert g.mode == "L"
    arr = np.asarray(g)
    assert arr[:, :10].mean() < 10     # opaque black stays black
    assert arr[:, -10:].mean() > 245   # transparent -> white


def test_apply_levels_increases_contrast(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.apply_levels(g, black=64, white=192, gamma=1.0)
    arr = np.asarray(out)
    assert arr.min() == 0 and arr.max() == 255   # clipped to full range


def test_fit_contain_centers_on_white_canvas(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    out = process.fit_contain(g, 100, 40, margin=5)
    assert out.size == (100, 40)
    arr = np.asarray(out)
    assert arr[0, 0] == 255 and arr[-1, -1] == 255   # corners are white padding


def test_fit_contain_scale_shrinks_content(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    full = process.fit_contain(g, 100, 100, margin=0, scale=1.0)
    small = process.fit_contain(g, 100, 100, margin=0, scale=0.5)
    # fewer non-white (content) pixels when scaled down
    assert (np.asarray(small) < 250).sum() < (np.asarray(full) < 250).sum()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_process.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lego_bin_labels.process'`

- [ ] **Step 3: Write the normalization half of `lego_bin_labels/process.py`**

```python
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps


def to_grayscale(rgba: Image.Image) -> Image.Image:
    """Flatten any transparency onto white, then desaturate to mode 'L'."""
    rgba = rgba.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    return bg.convert("L")


def apply_levels(g: Image.Image, black: int = 0, white: int = 255,
                 gamma: float = 1.0) -> Image.Image:
    """Map input range [black, white] to [0, 255] with optional gamma."""
    if white <= black:
        white = black + 1
    a = np.asarray(g, dtype=np.float64)
    a = (a - black) / (white - black)
    a = np.clip(a, 0.0, 1.0)
    if gamma != 1.0:
        a = a ** (1.0 / gamma)
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "L")


def fit_contain(g: Image.Image, w: int, h: int, margin: int = 6,
                scale: float = 1.0) -> Image.Image:
    """Scale g to fit within (w-2margin, h-2margin)*scale and center on white canvas.

    scale < 1 shrinks the part within the label, leaving extra breathing room.
    """
    scale = max(0.01, min(1.0, scale))
    inner = (max(1, round((w - 2 * margin) * scale)),
             max(1, round((h - 2 * margin) * scale)))
    scaled = ImageOps.contain(g, inner, Image.LANCZOS)
    canvas = Image.new("L", (w, h), 255)
    canvas.paste(scaled, ((w - scaled.width) // 2, (h - scaled.height) // 2))
    return canvas
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_process.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add lego_bin_labels/process.py tests/test_process.py
git commit -m "feat: add image normalization (flatten/grayscale/levels/fit)"
```

---

## Task 5: Dithering algorithms

**Files:**
- Modify: `lego_bin_labels/process.py`
- Test: `tests/test_process.py` (add cases)

- [ ] **Step 1: Add failing dither tests to `tests/test_process.py`**

```python
import pytest


def _to_1bit_array(img):
    assert img.mode == "1"
    return np.asarray(img.convert("L"))  # 0 or 255


def test_threshold_is_pure_black_and_white(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.dither(g, "threshold", threshold=128)
    vals = set(np.unique(_to_1bit_array(out)).tolist())
    assert vals <= {0, 255}
    # left (dark) side black, right (light) side white
    arr = _to_1bit_array(out)
    assert arr[:, 0].mean() == 0 and arr[:, -1].mean() == 255


@pytest.mark.parametrize("algo", ["floyd", "ordered", "atkinson"])
def test_dithers_produce_1bit_and_preserve_mean_brightness(gradient_rgba, algo):
    g = process.to_grayscale(gradient_rgba)
    out = process.dither(g, algo)
    vals = set(np.unique(_to_1bit_array(out)).tolist())
    assert vals <= {0, 255}
    # A gradient averages ~50% gray; error-diffusion keeps mean within tolerance.
    src_mean = np.asarray(g).mean() / 255
    out_mean = _to_1bit_array(out).mean() / 255
    assert abs(out_mean - src_mean) < 0.08


def test_unknown_algo_raises(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    with pytest.raises(ValueError):
        process.dither(g, "nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_process.py -k dither -v`
Expected: FAIL with `AttributeError: module 'lego_bin_labels.process' has no attribute 'dither'`

- [ ] **Step 3: Append dithering functions to `lego_bin_labels/process.py`**

```python
_BAYER4 = np.array(
    [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
    dtype=np.float64,
)


def dither_threshold(g: Image.Image, threshold: int = 128) -> Image.Image:
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")


def dither_floyd(g: Image.Image) -> Image.Image:
    return g.convert("1")  # Pillow's default is Floyd-Steinberg


def dither_ordered(g: Image.Image) -> Image.Image:
    n = 4
    thresh = (_BAYER4 + 0.5) / (n * n) * 255.0
    a = np.asarray(g, dtype=np.float64)
    reps = (a.shape[0] // n + 1, a.shape[1] // n + 1)
    tile = np.tile(thresh, reps)[: a.shape[0], : a.shape[1]]
    out = np.where(a > tile, 255, 0).astype(np.uint8)
    return Image.fromarray(out, "L").convert("1")


def dither_atkinson(g: Image.Image) -> Image.Image:
    a = np.asarray(g, dtype=np.float64).copy()
    h, w = a.shape
    for y in range(h):
        for x in range(w):
            old = a[y, x]
            new = 255.0 if old >= 128 else 0.0
            a[y, x] = new
            err = (old - new) / 8.0
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    a[ny, nx] += err
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L").convert("1")


_DITHERERS = {
    "threshold": dither_threshold,
    "floyd": dither_floyd,
    "ordered": dither_ordered,
    "atkinson": dither_atkinson,
}


def dither(g: Image.Image, algo: str, threshold: int = 128) -> Image.Image:
    if algo not in _DITHERERS:
        raise ValueError(f"unknown dither algo: {algo!r} (have {list(_DITHERERS)})")
    if algo == "threshold":
        return dither_threshold(g, threshold)
    return _DITHERERS[algo](g)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_process.py -v`
Expected: all passed (normalization + dither cases)

- [ ] **Step 5: Commit**

```bash
git add lego_bin_labels/process.py tests/test_process.py
git commit -m "feat: add threshold/floyd/ordered/atkinson dithering"
```

---

## Task 6: LDView render wrapper

**Files:**
- Create: `lego_bin_labels/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Write the failing tests (argv builder + part resolution are pure)**

`tests/test_render.py`:

```python
import os
import shutil
from pathlib import Path

import pytest
from PIL import Image

from lego_bin_labels.config import load_config
from lego_bin_labels import render


def test_resolve_part_id_to_parts_path(tmp_path):
    (tmp_path / "vendor/ldraw/parts").mkdir(parents=True)
    (tmp_path / "vendor/ldraw/parts/3001.dat").write_text("0 brick")
    cfg = load_config(root=tmp_path)
    assert render.resolve_part(cfg, "3001") == tmp_path / "vendor/ldraw/parts/3001.dat"


def test_resolve_part_accepts_explicit_path(tmp_path):
    f = tmp_path / "custom.ldr"
    f.write_text("0 x")
    cfg = load_config(root=tmp_path)
    assert render.resolve_part(cfg, str(f)) == f


def test_resolve_part_missing_raises(tmp_path):
    cfg = load_config(root=tmp_path)
    with pytest.raises(FileNotFoundError):
        render.resolve_part(cfg, "9999999")


def test_build_argv_shaded_uses_alpha_and_edges(tmp_path):
    cfg = load_config(root=tmp_path, overrides={"render_px": 800, "style": "shaded"})
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert argv[0] == "arch" and argv[1] == "-x86_64"
    assert str(cfg.ldview) in argv
    assert "-SaveSnapshot=/o/3001.png" in argv
    assert "-SaveWidth=800" in argv and "-SaveHeight=800" in argv
    assert "-SaveAlpha=1" in argv and "-AutoCrop=1" in argv
    assert "-EdgeLines=1" in argv
    assert f"-LDrawDir={cfg.ldraw_dir}" in argv


def test_build_argv_lineart_uses_white_surfaces(tmp_path):
    cfg = load_config(root=tmp_path, overrides={"style": "lineart"})
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    # line-art: white default color so only black edges survive a threshold
    assert "-DefaultColor3=0xFFFFFF" in argv
    assert "-EdgeLines=1" in argv


def test_build_argv_default_angle_is_iso():
    cfg = load_config(root=".")
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert "-DefaultLatLong=30.0,45.0" in argv
    assert "-Lighting=1" in argv  # normal shading


def test_build_argv_angle_preset_and_shading(tmp_path):
    cfg = load_config(root=tmp_path, overrides={"angle": "top", "shading": "flat"})
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert "-DefaultLatLong=90.0,0.0" in argv
    assert "-Lighting=0" in argv


def test_build_argv_explicit_latlong():
    cfg = load_config(root=".", overrides={"angle": "15,-60"})
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert "-DefaultLatLong=15.0,-60.0" in argv


def test_resolve_latlong_bad_value_raises():
    with pytest.raises(ValueError):
        render.resolve_latlong("sideways")


LDVIEW = Path("vendor/LDView.app/Contents/MacOS/LDView")


@pytest.mark.skipif(not LDVIEW.exists(), reason="LDView not installed (run scripts/setup-ldview.sh)")
def test_render_part_live_produces_rgba_png(tmp_path):
    cfg = load_config(root=Path.cwd())
    out = tmp_path / "3001.png"
    render.render_part(cfg, "3001", out)
    assert out.exists()
    im = Image.open(out)
    assert im.mode == "RGBA" and im.width > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lego_bin_labels.render'`

- [ ] **Step 3: Write `lego_bin_labels/render.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config

# Viewing-angle presets -> LDView (latitude, longitude) degrees.
ANGLE_PRESETS = {
    "iso": (30.0, 45.0),     # 45-degree isometric (default)
    "front": (0.0, 0.0),
    "back": (0.0, 180.0),
    "left": (0.0, -90.0),
    "right": (0.0, 90.0),
    "top": (90.0, 0.0),
    "bottom": (-90.0, 0.0),
}

# Shading mode -> extra LDView flags.
SHADING_FLAGS = {
    "normal": ["-Lighting=1"],
    "flat": ["-Lighting=0"],
    "subdued": ["-Lighting=1", "-SubduedLighting=1"],
}


def resolve_latlong(angle: str) -> tuple[float, float]:
    """Resolve an angle preset name or explicit 'LAT,LONG' string to degrees."""
    if angle in ANGLE_PRESETS:
        return ANGLE_PRESETS[angle]
    try:
        lat, long = (float(x) for x in angle.split(","))
        return lat, long
    except (ValueError, TypeError):
        raise ValueError(
            f"bad angle {angle!r}: use a preset {list(ANGLE_PRESETS)} or 'LAT,LONG'"
        )


def resolve_part(cfg: Config, part: str) -> Path:
    """Resolve a part id or explicit path to an LDraw file."""
    p = Path(part)
    if p.suffix.lower() in (".dat", ".ldr", ".mpd") and p.exists():
        return p
    candidate = cfg.ldraw_dir / "parts" / f"{part}.dat"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"could not resolve part {part!r} (looked for {candidate})")


def build_argv(cfg: Config, part_file: Path, out_png: Path) -> list[str]:
    """Build the LDView snapshot command line (x86_64 via Rosetta on Apple Silicon)."""
    argv = [
        "arch", "-x86_64", str(cfg.ldview),
        str(part_file),
        f"-LDrawDir={cfg.ldraw_dir}",
        f"-SaveSnapshot={out_png}",
        f"-SaveWidth={cfg.render_px}",
        f"-SaveHeight={cfg.render_px}",
        "-AutoCrop=1",
        "-SaveAlpha=1",
        "-EdgeLines=1",
    ]
    lat, long = resolve_latlong(cfg.angle)
    argv.append(f"-DefaultLatLong={lat},{long}")
    argv.extend(SHADING_FLAGS.get(cfg.shading, SHADING_FLAGS["normal"]))
    if cfg.style == "lineart":
        # White surfaces so only the black edge lines remain after thresholding.
        argv.append("-DefaultColor3=0xFFFFFF")
    return argv


def render_part(cfg: Config, part: str, out_png: Path) -> Path:
    """Render a part to a transparent hi-res PNG. Returns out_png."""
    part_file = resolve_part(cfg, part)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    argv = build_argv(cfg, part_file, out_png)
    subprocess.run(argv, check=True, capture_output=True)
    if not out_png.exists():
        raise RuntimeError(f"LDView did not write {out_png}")
    return out_png
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_render.py -v`
Expected: 5 passed, 1 skipped if LDView absent — or 6 passed if `scripts/setup-ldview.sh` has been run.

- [ ] **Step 5: Commit**

```bash
git add lego_bin_labels/render.py tests/test_render.py
git commit -m "feat: add LDView render wrapper (argv builder + live snapshot)"
```

---

## Task 7: CLI — single part, output modes, sizing

**Files:**
- Create: `lego_bin_labels/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests (render mocked so no LDView needed)**

`tests/test_cli.py`:

```python
from pathlib import Path

import numpy as np
from PIL import Image

from lego_bin_labels import cli


def _fake_render(monkeypatch, src_size=(400, 300)):
    """Patch render_part to drop a fixed RGBA file instead of calling LDView."""
    def fake(cfg, part, out_png):
        out_png.parent.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((src_size[1], src_size[0], 4), dtype=np.uint8)
        arr[50:-50, 50:-50] = (90, 90, 90, 255)  # gray block, opaque
        Image.fromarray(arr, "RGBA").save(out_png)
        return out_png
    monkeypatch.setattr(cli.render, "render_part", fake)


def test_mode_both_writes_gray_and_mono(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    rc = cli.main(["3001", "--mode", "both", "--out", str(tmp_path), "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "3001.gray.png").exists()
    assert (tmp_path / "3001.mono.png").exists()
    assert Image.open(tmp_path / "3001.mono.png").mode == "1"


def test_mode_gray_only(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "gray", "--out", str(tmp_path), "--root", str(tmp_path)])
    assert (tmp_path / "3001.gray.png").exists()
    assert not (tmp_path / "3001.mono.png").exists()


def test_mono_size_respects_width_height(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "mono", "--width", "120", "--height", "80",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert Image.open(tmp_path / "3001.mono.png").size == (120, 80)


def test_debug_dir_saves_intermediates(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    dbg = tmp_path / "dbg"
    cli.main(["3001", "--mode", "mono", "--out", str(tmp_path),
              "--root", str(tmp_path), "--debug-dir", str(dbg)])
    assert (dbg / "render" / "3001.png").exists()
    assert (dbg / "gray" / "3001.png").exists()
    assert (dbg / "mono" / "3001.png").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lego_bin_labels.cli'`

- [ ] **Step 3: Write `lego_bin_labels/cli.py`**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from . import render, process
from .config import load_config, Config


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="lego-bin-labels",
                                description="Render LEGO parts into bin-label bitmaps.")
    p.add_argument("parts", nargs="*", help="part ids or .dat/.ldr paths")
    p.add_argument("--list", help="file with one part per line (overrides positional)")
    p.add_argument("--out", default="out", help="output directory")
    p.add_argument("--root", default=".", help="project root holding vendor/ and labels.toml")
    p.add_argument("--config", default=None, help="path to labels.toml")
    p.add_argument("--mode", choices=["gray", "mono", "both"])
    p.add_argument("--dither", choices=["threshold", "floyd", "ordered", "atkinson"])
    p.add_argument("--style", choices=["shaded", "lineart"])
    p.add_argument("--angle", help="iso|front|back|left|right|top|bottom or 'LAT,LONG'")
    p.add_argument("--shading", choices=["normal", "flat", "subdued"])
    p.add_argument("--scale", type=float, help="part fill fraction of view area (0-1)")
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--dpi", type=int)
    p.add_argument("--label-mm", type=float, nargs=2, metavar=("W", "H"))
    p.add_argument("--margin", type=int)
    p.add_argument("--threshold", type=int)
    p.add_argument("--gamma", type=float)
    p.add_argument("--levels", type=int, nargs=2, metavar=("BLACK", "WHITE"))
    p.add_argument("--debug-dir", default=None, help="save every pipeline stage here")
    return p.parse_args(argv)


def _config_from_args(args) -> Config:
    toml = args.config or str(Path(args.root) / "labels.toml")
    overrides = {
        "mode": args.mode, "dither": args.dither, "style": args.style,
        "angle": args.angle, "shading": args.shading, "scale": args.scale,
        "width": args.width, "height": args.height, "dpi": args.dpi,
        "label_mm": tuple(args.label_mm) if args.label_mm else None,
        "margin": args.margin, "threshold": args.threshold,
        "gamma": args.gamma,
        "levels": tuple(args.levels) if args.levels else None,
    }
    return load_config(toml_path=toml, overrides=overrides, root=args.root)


def _stage_path(debug_dir, stage, name):
    d = Path(debug_dir) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.png"


def process_one(cfg: Config, part: str, out_dir: Path, debug_dir=None) -> None:
    name = Path(part).stem if Path(part).suffix else part
    render_png = (_stage_path(debug_dir, "render", name) if debug_dir
                  else out_dir / f"{name}.render.png")
    render.render_part(cfg, part, render_png)

    gray_full = process.to_grayscale(Image.open(render_png))
    if cfg.levels:
        gray_full = process.apply_levels(gray_full, cfg.levels[0], cfg.levels[1], cfg.gamma)
    elif cfg.gamma != 1.0:
        gray_full = process.apply_levels(gray_full, 0, 255, cfg.gamma)

    if debug_dir:
        gray_full.save(_stage_path(debug_dir, "gray", name))

    out_dir.mkdir(parents=True, exist_ok=True)
    if cfg.mode in ("gray", "both"):
        gray_full.save(out_dir / f"{name}.gray.png")

    if cfg.mode in ("mono", "both"):
        fitted = process.fit_contain(gray_full, cfg.width, cfg.height,
                                     cfg.margin, cfg.scale)
        mono = process.dither(fitted, cfg.dither, cfg.threshold)
        if debug_dir:
            mono.save(_stage_path(debug_dir, "mono", name))
        mono.save(out_dir / f"{name}.mono.png")

    if not debug_dir and render_png.exists():
        render_png.unlink()  # drop the scratch render unless debugging


def _gather_parts(args) -> list[str]:
    if args.list:
        return [ln.strip() for ln in Path(args.list).read_text().splitlines()
                if ln.strip() and not ln.startswith("#")]
    return args.parts


def main(argv=None) -> int:
    args = _parse_args(argv)
    cfg = _config_from_args(args)
    parts = _gather_parts(args)
    if not parts:
        print("no parts given")
        return 2
    out_dir = Path(args.out)
    for part in parts:
        process_one(cfg, part, out_dir, debug_dir=args.debug_dir)
        print(f"done: {part}")
    return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add lego_bin_labels/cli.py tests/test_cli.py
git commit -m "feat: add CLI with gray/mono/both modes and debug-dir"
```

---

## Task 8: CLI batch via list file

**Files:**
- Modify: none (already supported by `--list`/`_gather_parts`)
- Test: `tests/test_cli.py` (add a batch case)

- [ ] **Step 1: Add failing batch test to `tests/test_cli.py`**

```python
def test_batch_list_file_processes_each_part(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    listing = tmp_path / "parts.txt"
    listing.write_text("# bins\n3001\n3002\n\n")
    rc = cli.main(["--list", str(listing), "--mode", "mono",
                   "--out", str(tmp_path), "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "3001.mono.png").exists()
    assert (tmp_path / "3002.mono.png").exists()
```

- [ ] **Step 2: Run to verify it passes (functionality already present)**

Run: `.venv/bin/pytest tests/test_cli.py::test_batch_list_file_processes_each_part -v`
Expected: PASS. If it fails, fix `_gather_parts` to skip blank/`#` lines per the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: cover batch list-file processing"
```

---

## Task 9: End-to-end live test, README, PROJECTS.md

**Files:**
- Create: live-render check (no new code), `README.md` (expand)
- Modify: `~/src/PROJECTS.md`

- [ ] **Step 1: Run the full pipeline live (requires setup script already run)**

Run:

```bash
.venv/bin/python -m lego_bin_labels.cli 3001 3003 \
  --mode both --dither atkinson --out out --debug-dir debug --root .
ls out/ debug/*/
```

Expected: `out/3001.gray.png out/3001.mono.png out/3003.gray.png out/3003.mono.png`
and `debug/render/ debug/gray/ debug/mono/` populated.

- [ ] **Step 2: Eyeball the dither tuning**

Open `out/3001.mono.png` and `debug/gray/3001.png`. If the brick reads too dark
(LDView's default lighting is mid-gray, per the spec's smoke-test finding), re-run
with levels, e.g.:

```bash
.venv/bin/python -m lego_bin_labels.cli 3001 --mode mono \
  --levels 40 200 --gamma 1.2 --out out --root .
```

Record the values that look best in `labels.toml`.

- [ ] **Step 3: Expand `README.md`**

```markdown
# lego-bin-labels

Render LEGO parts from LDraw (via LDView) into monochrome dithered bitmaps or
high-res grayscale images for Brother P-touch (LBX) bin labels.

## Setup (macOS)

    python3 -m venv .venv && .venv/bin/pip install -e .
    ./scripts/setup-ldview.sh        # installs vendor/LDView.app + vendor/ldraw

LDView ships x86_64-only; on Apple Silicon it runs under Rosetta automatically.

## Usage

    # one part, both outputs
    .venv/bin/python -m lego_bin_labels.cli 3001 --mode both --out out

    # batch from a list file, 1-bit Atkinson dither at 360 dpi
    .venv/bin/python -m lego_bin_labels.cli --list bins.txt \
        --mode mono --dither atkinson --dpi 360 --out out

    # size by physical tape instead of pixels
    .venv/bin/python -m lego_bin_labels.cli 3001 --label-mm 24 12 --mode mono

    # top-down flat-shaded line art, part filling 80% of the label
    .venv/bin/python -m lego_bin_labels.cli 3001 --angle top --shading flat \
        --style lineart --dither threshold --scale 0.8 --mode mono

Modes: `gray` (driver dithers), `mono` (1-bit dithered here), `both`.
Dithers: `threshold`, `floyd`, `ordered`, `atkinson`.
Angle: `iso` (default) | `front` | `back` | `left` | `right` | `top` | `bottom` | `LAT,LONG`.
Shading: `normal` | `flat` | `subdued`.  `--scale 0-1` sets how much of the label the part fills.
Use `--debug-dir DIR` to dump every pipeline stage for comparison.

See `docs/superpowers/specs/` for the design.
```

- [ ] **Step 4: Add a one-line entry to `~/src/PROJECTS.md`** under `## Personal`:

```
- **lego-bin-labels** — Python CLI rendering LEGO parts from LDraw (LDView under Rosetta) into 1-bit dithered or hi-res grayscale bitmaps for Brother P-touch (LBX) bin labels. Pure image-processing core + thin LDView wrapper.
```

- [ ] **Step 5: Run the whole suite once more**

Run: `.venv/bin/pytest -q`
Expected: all passing (live render test passes if setup script was run, else skipped).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: usage README for lego-bin-labels"
# PROJECTS.md lives outside this repo; commit it in ~/src if that is a repo,
# otherwise just save the edit.
```

---

## Notes for the implementer

- **macOS only.** Render relies on `arch -x86_64`, `hdiutil`, and the LDView `.app`. The pure `process.py`/`config.py` tests run anywhere; the live render test self-skips when `vendor/LDView.app` is absent.
- **Focus:** the live LDView snapshot has not been observed to steal window focus, but confirm during Task 9; if it flashes a window, note it — do not add hacks unless it actually disrupts.
- **Atkinson is O(width·height) in Python** — fine at label sizes (≤ ~360px). Do not run it on the full 1024px render; it only ever sees the fitted label image.
- **Tuning is expected work** (Task 9 Step 2): LDView's default lighting renders parts mid-gray. Levels/gamma and possibly `--style lineart` are the levers. This is the experimentation surface the user explicitly asked for.
