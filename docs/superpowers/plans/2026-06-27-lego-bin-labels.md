# brick-icons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone Python CLI that renders LEGO parts from LDraw via LDView and emits bin-label assets in several styles (normal/cel/outline) and formats (grayscale PNG, 1-bit dithered PNG, color PNG, and SVG) sized for a Brother P-touch label.

**Architecture:** A pure, unit-testable image core (`process.py`) and vector core (`trace.py`), a thin LDView subprocess wrapper (`render.py`), a config loader (`config.py`), and a CLI (`cli.py`) that wires part inputs to label outputs. LDView renders transparent RGBA at high supersample + max curve fidelity + contrast lighting; Pillow handles styling/dithering; potrace handles vectorization.

**Tech Stack:** Python 3.11+ (`tomllib`, `argparse`, `subprocess`), Pillow, NumPy. LDView 4.2.1 (SourceForge dmg, x86_64 under Rosetta). LDraw `complete.zip`. `potrace` (SVG). ImageMagick (SVG preview in tests). macOS.

---

## Validated facts (from spec smoke-tests — do not re-litigate)

- LDView is **x86_64-only** on macOS; invoke via `arch -x86_64 vendor/LDView.app/Contents/MacOS/LDView`. Rosetta is installed.

## Portability (designed in — keep platform specifics in config, not code)

Only the LDView *invocation* is platform-specific. Abstract it:
- `config.ldview` — path to the LDView binary (default macOS `.app` path; on Linux set to e.g. `/usr/bin/ldview` via `labels.toml`).
- `config.ldview_launcher` — list of prefix args before the binary (default `["arch","-x86_64"]` on Apple Silicon macOS, `[]` elsewhere, computed by `default_ldview_launcher()`; overridable in `labels.toml`).
All LDView `-Flags` are identical across LDView's macOS/Linux/Windows builds, so the rest of the code is already portable. potrace, ImageMagick, Pillow, NumPy are cross-platform. The setup *script* is macOS-only (dmg/hdiutil/brew) and documented as such; on Linux you install ldview + potrace via the package manager and point `labels.toml` at them.
- Render flags that work: `-SaveSnapshot -SaveWidth/-SaveHeight -AutoCrop=1 -SaveAlpha=1 -EdgeLines=1 -DefaultLatLong=LAT,LONG -CurveQuality=12 -HiResPrimitives=1 -AllowPrimitiveSubstitution=1 -Lighting=1 -UseQualityLighting=1 -LightVector=-1,1,2 -DefaultColor3=0xRRGGBB`.
- Render transparent, flatten on white in Pillow.
- potrace emits paths inside `<g transform="translate(0,H) scale(0.1,-0.1)">`; **preserve that transform** when assembling multi-band SVGs.

## File Structure

```
brick-icons/
  pyproject.toml                 # deps: pillow, numpy
  labels.toml                    # default config
  README.md
  .gitignore                     # vendor/, out/, debug/, .venv/
  scripts/setup-ldview.sh        # install LDView.app + LDraw lib; check potrace
  brick_icons/
    __init__.py
    config.py                    # load labels.toml + overrides -> Config
    render.py                    # resolve part, build LDView argv, run snapshot
    process.py                   # flatten/gray/levels/posterize/outline/fit/dither
    trace.py                     # potrace outline_svg + cel_svg
    cli.py                       # argparse, format/mode/shading wiring, batch
  tests/
    conftest.py
    test_config.py
    test_process.py
    test_render.py               # argv builder (unit) + live render (skip if no LDView)
    test_trace.py                # potrace SVG (skip if potrace absent)
    test_cli.py                  # wiring with render mocked
  vendor/                        # gitignored: LDView.app, ldraw/
```

---

## Task 1: Project scaffold and dependencies

**Files:** Create `pyproject.toml`, `brick_icons/__init__.py`, `tests/conftest.py`; modify `.gitignore`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "brick-icons"
version = "0.1.0"
description = "Render LEGO parts from LDraw into bin-label bitmaps and SVGs"
requires-python = ">=3.11"
dependencies = ["pillow>=10", "numpy>=1.26"]

[project.scripts]
brick-icons = "brick_icons.cli:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["brick_icons*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `brick_icons/__init__.py`**

```python
"""Render LEGO parts from LDraw into bin-label bitmaps and SVGs."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Append to `.gitignore`**

```
vendor/
.venv/
.pytest_cache/
```

- [ ] **Step 4: Create venv and install**

Run:
```bash
cd ~/src/brick-icons
python3 -m venv .venv
.venv/bin/pip install -q -e . && .venv/bin/pip install -q pytest
.venv/bin/python -c "import PIL, numpy; print('deps ok')"
```
Expected: `deps ok`

- [ ] **Step 5: Create `tests/conftest.py`**

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
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml brick_icons/__init__.py tests/conftest.py .gitignore
git commit -m "chore: scaffold brick-icons package and test deps"
```

---

## Task 2: LDView + LDraw + potrace setup script

**Files:** Create `scripts/setup-ldview.sh`. I/O-heavy; verified by running, not unit-tested. Idempotent.

- [ ] **Step 1: Write `scripts/setup-ldview.sh`**

```bash
#!/usr/bin/env bash
# Install LDView.app + LDraw library into ./vendor; verify potrace. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
VENDOR="$PWD/vendor"; mkdir -p "$VENDOR"

DMG_URL="https://downloads.sourceforge.net/project/ldview/01.%20LDView/LDView%204.2/LDView_4.2.1_Universal.dmg?viasf=1"
LDRAW_URL="https://library.ldraw.org/library/updates/complete.zip"

if [ ! -x "$VENDOR/LDView.app/Contents/MacOS/LDView" ]; then
  echo "Downloading LDView dmg..."
  curl -sL -o "$VENDOR/LDView.dmg" "$DMG_URL"
  MNT="$VENDOR/.ldview-mnt"; mkdir -p "$MNT"
  hdiutil attach "$VENDOR/LDView.dmg" -nobrowse -noverify -mountpoint "$MNT" >/dev/null
  rm -rf "$VENDOR/LDView.app"; cp -R "$MNT/LDView.app" "$VENDOR/LDView.app"
  hdiutil detach "$MNT" >/dev/null; rm -f "$VENDOR/LDView.dmg"
  xattr -dr com.apple.quarantine "$VENDOR/LDView.app" 2>/dev/null || true
  echo "LDView installed."
else
  echo "LDView already present."
fi

if [ ! -f "$VENDOR/ldraw/parts/3001.dat" ]; then
  echo "Downloading LDraw complete.zip (~140 MB)..."
  curl -sL -o "$VENDOR/complete.zip" "$LDRAW_URL"
  rm -rf "$VENDOR/ldraw"; unzip -q -o "$VENDOR/complete.zip" -d "$VENDOR"
  rm -f "$VENDOR/complete.zip"; echo "LDraw library installed."
else
  echo "LDraw library already present."
fi

if ! command -v potrace >/dev/null 2>&1; then
  echo "potrace not found -> installing (needed for SVG output)"; brew install potrace
fi

test -x "$VENDOR/LDView.app/Contents/MacOS/LDView"
test -f "$VENDOR/ldraw/parts/3001.dat"
command -v potrace >/dev/null
echo "Setup OK: LDView, LDraw, potrace."
```

- [ ] **Step 2: Run it**

```bash
chmod +x scripts/setup-ldview.sh && ./scripts/setup-ldview.sh
```
Expected final line: `Setup OK: LDView, LDraw, potrace.`

- [ ] **Step 3: Live render smoke check**

```bash
arch -x86_64 vendor/LDView.app/Contents/MacOS/LDView \
  vendor/ldraw/parts/3001.dat -LDrawDir="$PWD/vendor/ldraw" \
  -SaveSnapshot="$PWD/vendor/_smoke.png" -SaveWidth=256 -SaveHeight=256 \
  -AutoCrop=1 -SaveAlpha=1 ; file vendor/_smoke.png ; rm -f vendor/_smoke.png
```
Expected: `PNG image data, ... RGBA ...`

- [ ] **Step 4: Commit**

```bash
git add scripts/setup-ldview.sh
git commit -m "feat: add LDView + LDraw + potrace setup script"
```

---

## Task 3: Config loader

**Files:** Create `brick_icons/config.py`, `labels.toml`. Test `tests/test_config.py`.

- [ ] **Step 1: Write `tests/test_config.py`**

```python
from pathlib import Path
from brick_icons.config import load_config


def test_defaults():
    cfg = load_config(root="/proj")
    assert cfg.dpi == 180 and cfg.mode == "both" and cfg.fmt == "png"
    assert cfg.dither == "atkinson" and cfg.shading == "normal"
    assert cfg.width == 256 and cfg.height == 170
    assert cfg.render_px == 2048 and cfg.curve_quality == 12
    assert cfg.angle == "iso" and cfg.cel_levels == 4
    assert cfg.outline_interior is True and cfg.part_color is None
    assert cfg.scale == 1.0
    assert cfg.ldraw_dir == Path("/proj/vendor/ldraw")
    assert cfg.ldview == Path("/proj/vendor/LDView.app/Contents/MacOS/LDView")
    assert isinstance(cfg.ldview_launcher, tuple)   # platform-detected prefix


def test_default_launcher_by_platform():
    from brick_icons.config import default_ldview_launcher
    assert default_ldview_launcher("Darwin", "arm64") == ["arch", "-x86_64"]
    assert default_ldview_launcher("Darwin", "x86_64") == []
    assert default_ldview_launcher("Linux", "x86_64") == []


def test_launcher_override():
    cfg = load_config(overrides={"ldview_launcher": []}, root="/p")
    assert cfg.ldview_launcher == ()


def test_overrides_win_and_none_ignored():
    cfg = load_config(overrides={"dpi": 360, "shading": "cel", "width": None}, root="/p")
    assert cfg.dpi == 360 and cfg.shading == "cel"
    assert cfg.width == 256  # None ignored


def test_label_mm_to_pixels():
    cfg = load_config(overrides={"label_mm": (24.0, 12.0), "dpi": 180}, root="/p")
    assert cfg.width == round(24.0 / 25.4 * 180)
    assert cfg.height == round(12.0 / 25.4 * 180)


def test_toml_used(tmp_path):
    t = tmp_path / "labels.toml"
    t.write_text('dpi = 360\nshading = "outline"\ncel_levels = 6\n')
    cfg = load_config(toml_path=str(t), root="/p")
    assert cfg.dpi == 360 and cfg.shading == "outline" and cfg.cel_levels == 6
```

- [ ] **Step 2: Run — expect fail**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'brick_icons.config'`

- [ ] **Step 3: Write `brick_icons/config.py`**

```python
from __future__ import annotations

import platform as _platform
import tomllib
from dataclasses import dataclass
from pathlib import Path

MM_PER_INCH = 25.4


def default_ldview_launcher(system: str | None = None, machine: str | None = None) -> list[str]:
    """Prefix args to launch LDView. macOS ships only an x86_64 build, so run it
    under Rosetta on Apple Silicon; everywhere else, run the binary directly."""
    system = system or _platform.system()
    machine = machine or _platform.machine()
    if system == "Darwin" and machine == "arm64":
        return ["arch", "-x86_64"]
    return []


DEFAULTS = {
    "ldview": "vendor/LDView.app/Contents/MacOS/LDView",
    "ldview_launcher": None,   # None -> default_ldview_launcher(); [] to force direct
    "ldraw_dir": "vendor/ldraw",
    "dpi": 180,
    "label_mm": None,        # (w_mm, h_mm) or None
    "width": 256,            # px (ignored if label_mm)
    "height": 170,
    "margin": 6,
    "render_px": 2048,       # LDView supersample square
    "curve_quality": 12,     # LDView curve subdivision (max)
    "angle": "iso",          # preset or "LAT,LONG"
    "shading": "normal",     # normal | cel | outline
    "cel_levels": 4,         # bands for cel shading
    "outline_interior": True,# include interior edges in outline
    "part_color": None,      # "0xRRGGBB" or None
    "scale": 1.0,            # part fill fraction of label (0-1)
    "fmt": "png",            # png | svg | both
    "mode": "both",          # gray | mono | color | both  (png only)
    "dither": "atkinson",    # threshold | floyd | ordered | atkinson
    "threshold": 128,
    "gamma": 1.0,
    "levels": None,          # (black_in, white_in) or None
}


@dataclass(frozen=True)
class Config:
    ldview: Path
    ldview_launcher: tuple
    ldraw_dir: Path
    dpi: int
    width: int
    height: int
    margin: int
    render_px: int
    curve_quality: int
    angle: str
    shading: str
    cel_levels: int
    outline_interior: bool
    part_color: str | None
    scale: float
    fmt: str
    mode: str
    dither: str
    threshold: int
    gamma: float
    levels: tuple | None


def load_config(toml_path=None, overrides=None, root="."):
    data = dict(DEFAULTS)
    if toml_path and Path(toml_path).exists():
        with open(toml_path, "rb") as f:
            data.update(tomllib.load(f))
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    root = Path(root)
    if data.get("label_mm"):
        w_mm, h_mm = data["label_mm"]
        data["width"] = round(w_mm / MM_PER_INCH * data["dpi"])
        data["height"] = round(h_mm / MM_PER_INCH * data["dpi"])

    launcher = data["ldview_launcher"]
    if launcher is None:
        launcher = default_ldview_launcher()

    return Config(
        ldview=root / data["ldview"],
        ldview_launcher=tuple(launcher),
        ldraw_dir=root / data["ldraw_dir"],
        dpi=int(data["dpi"]),
        width=int(data["width"]),
        height=int(data["height"]),
        margin=int(data["margin"]),
        render_px=int(data["render_px"]),
        curve_quality=int(data["curve_quality"]),
        angle=str(data["angle"]),
        shading=str(data["shading"]),
        cel_levels=int(data["cel_levels"]),
        outline_interior=bool(data["outline_interior"]),
        part_color=(str(data["part_color"]) if data["part_color"] else None),
        scale=float(data["scale"]),
        fmt=str(data["fmt"]),
        mode=str(data["mode"]),
        dither=str(data["dither"]),
        threshold=int(data["threshold"]),
        gamma=float(data["gamma"]),
        levels=tuple(data["levels"]) if data["levels"] else None,
    )
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/test_config.py -v`  → 4 passed

- [ ] **Step 5: Create `labels.toml`**

```toml
# Default config for brick-icons. CLI flags override these.
dpi = 180
margin = 6
render_px = 2048       # LDView supersample before downscale
curve_quality = 12     # LDView curve subdivision (max); 48-seg hi-res primitives
angle = "iso"          # iso|front|back|left|right|top|bottom or "LAT,LONG"
shading = "normal"     # normal | cel | outline
cel_levels = 4         # bands for cel shading
outline_interior = true
fmt = "png"            # png | svg | both
mode = "both"          # gray | mono | color | both
dither = "atkinson"    # threshold | floyd | ordered | atkinson
threshold = 128
gamma = 1.0
# part_color = "0xC0C0C0"
# label_mm = [24.0, 12.0]
#
# --- Portability ---
# On Linux/Windows, point at a native LDView and disable the Rosetta prefix:
# ldview = "/usr/bin/ldview"
# ldview_launcher = []
```

- [ ] **Step 6: Commit**

```bash
git add brick_icons/config.py labels.toml tests/test_config.py
git commit -m "feat: add config loader (fidelity/shading/format defaults)"
```

---

## Task 4: Image core — flatten, levels, posterize, fit, outline

**Files:** Create `brick_icons/process.py`. Test `tests/test_process.py`.

- [ ] **Step 1: Write `tests/test_process.py`**

```python
import numpy as np
import pytest
from PIL import Image
from brick_icons import process


def test_to_grayscale_flattens_onto_white(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    assert g.mode == "L"
    a = np.asarray(g)
    assert a[:, :10].mean() < 120     # gray part
    assert a[:, -10:].mean() > 245    # transparent -> white


def test_flatten_rgb_keeps_color():
    arr = np.zeros((10, 10, 4), np.uint8)
    arr[:, :, 0] = 200; arr[:, :, 3] = 255   # opaque red
    rgb = process.flatten_rgb(Image.fromarray(arr, "RGBA"))
    assert rgb.mode == "RGB"
    assert np.asarray(rgb)[..., 0].mean() > 150


def test_apply_levels_increases_contrast(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.apply_levels(g, 64, 192, 1.0)
    a = np.asarray(out)
    assert a.min() == 0 and a.max() == 255


def test_posterize_reduces_unique_levels(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    out = process.posterize(g, 4)
    assert len(set(np.unique(out).tolist())) <= 4


def test_fit_contain_centers_and_scales(half_transparent_rgba):
    g = process.to_grayscale(half_transparent_rgba)
    out = process.fit_contain(g, 100, 40, margin=5, scale=1.0)
    assert out.size == (100, 40)
    a = np.asarray(out)
    assert a[0, 0] == 255 and a[-1, -1] == 255
    small = process.fit_contain(g, 100, 100, margin=0, scale=0.5)
    assert (np.asarray(small) < 250).sum() < (np.asarray(process.fit_contain(g, 100, 100, margin=0, scale=1.0)) < 250).sum()


def test_make_outline_is_black_lines_on_white(disc_rgba):
    out = process.make_outline(disc_rgba, interior=False)
    assert out.mode == "L"
    a = np.asarray(out)
    assert (a == 0).any() and (a == 255).any()   # has lines and white
    assert a.mean() > 200                          # mostly white (it's an outline)


def test_make_outline_interior_adds_pixels(gradient_rgba):
    # an opaque gradient block: interior edges add line pixels vs silhouette-only
    sil = np.asarray(process.make_outline(gradient_rgba, interior=False))
    full = np.asarray(process.make_outline(gradient_rgba, interior=True))
    assert (full == 0).sum() >= (sil == 0).sum()
```

- [ ] **Step 2: Run — expect fail** (`No module named 'brick_icons.process'`)

- [ ] **Step 3: Write `brick_icons/process.py`**

```python
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps


def flatten_rgb(rgba: Image.Image) -> Image.Image:
    rgba = rgba.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    bg.alpha_composite(rgba)
    return bg.convert("RGB")


def to_grayscale(rgba: Image.Image) -> Image.Image:
    return flatten_rgb(rgba).convert("L")


def apply_levels(g: Image.Image, black: int = 0, white: int = 255,
                 gamma: float = 1.0) -> Image.Image:
    if white <= black:
        white = black + 1
    a = np.asarray(g, np.float64)
    a = np.clip((a - black) / (white - black), 0.0, 1.0)
    if gamma != 1.0:
        a = a ** (1.0 / gamma)
    return Image.fromarray((a * 255.0 + 0.5).astype(np.uint8), "L")


def posterize(g: Image.Image, levels: int = 4) -> Image.Image:
    levels = max(2, levels)
    a = np.asarray(g, np.float64)
    q = np.round(a / 255 * (levels - 1)) / (levels - 1) * 255
    return Image.fromarray(np.round(q).astype(np.uint8), "L")  # round, not truncate


def fit_contain(g: Image.Image, w: int, h: int, margin: int = 6,
                scale: float = 1.0) -> Image.Image:
    scale = max(0.01, min(1.0, scale))
    inner = (max(1, round((w - 2 * margin) * scale)),
             max(1, round((h - 2 * margin) * scale)))
    scaled = ImageOps.contain(g, inner, Image.LANCZOS)
    canvas = Image.new("L", (w, h), 255)
    canvas.paste(scaled, ((w - scaled.width) // 2, (h - scaled.height) // 2))
    return canvas


def _silhouette_mask(rgba: Image.Image, thr: int = 16) -> Image.Image:
    return rgba.convert("RGBA").split()[-1].point(lambda p: 255 if p > thr else 0)


def make_outline(rgba: Image.Image, interior: bool = True,
                 sil_w: int = 2, edge_thr: int = 28) -> Image.Image:
    """Black line-art on white: silhouette contour + optional interior edges."""
    rgba = rgba.convert("RGBA")
    a = _silhouette_mask(rgba)
    dil = a.filter(ImageFilter.MaxFilter(sil_w * 2 + 1))
    ero = a.filter(ImageFilter.MinFilter(sil_w * 2 + 1))
    lines = (np.asarray(dil, int) - np.asarray(ero, int)) > 0
    if interior:
        g = to_grayscale(rgba)
        edges = np.asarray(g.filter(ImageFilter.FIND_EDGES), int)
        inside = np.asarray(a, int) > 16
        lines = lines | ((edges > edge_thr) & inside)
    return Image.fromarray(np.where(lines, 0, 255).astype(np.uint8), "L")


_BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
                   dtype=np.float64)


def dither_threshold(g: Image.Image, threshold: int = 128) -> Image.Image:
    return g.point(lambda p: 255 if p >= threshold else 0).convert("1")


def dither_floyd(g: Image.Image) -> Image.Image:
    return g.convert("1")


def dither_ordered(g: Image.Image) -> Image.Image:
    n = 4
    thresh = (_BAYER4 + 0.5) / (n * n) * 255.0
    a = np.asarray(g, np.float64)
    tile = np.tile(thresh, (a.shape[0] // n + 1, a.shape[1] // n + 1))[:a.shape[0], :a.shape[1]]
    return Image.fromarray(np.where(a > tile, 255, 0).astype(np.uint8), "L").convert("1")


def dither_atkinson(g: Image.Image) -> Image.Image:
    a = np.asarray(g, np.float64).copy()
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


_DITHERERS = {"threshold": dither_threshold, "floyd": dither_floyd,
              "ordered": dither_ordered, "atkinson": dither_atkinson}


def dither(g: Image.Image, algo: str, threshold: int = 128) -> Image.Image:
    if algo not in _DITHERERS:
        raise ValueError(f"unknown dither algo: {algo!r} (have {list(_DITHERERS)})")
    if algo == "threshold":
        return dither_threshold(g, threshold)
    return _DITHERERS[algo](g)
```

- [ ] **Step 4: Run — expect pass**

Run: `.venv/bin/pytest tests/test_process.py -v`  → all passed

- [ ] **Step 5: Commit**

```bash
git add brick_icons/process.py tests/test_process.py
git commit -m "feat: image core (flatten/levels/posterize/outline/fit/dither)"
```

---

## Task 5: Dither behavior tests (lock semantics)

**Files:** Modify `tests/test_process.py` (add dither cases). No new source — `dither()` exists from Task 4.

- [ ] **Step 1: Add dither tests**

```python
def _arr1(img):
    assert img.mode == "1"
    return np.asarray(img.convert("L"))


def test_threshold_pure_bw(gradient_rgba):
    g = process.to_grayscale(gradient_rgba)
    a = _arr1(process.dither(g, "threshold", 128))
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert a[:, 0].mean() == 0 and a[:, -1].mean() == 255


@pytest.mark.parametrize("algo", ["floyd", "ordered", "atkinson"])
def test_dithers_preserve_mean(gradient_rgba, algo):
    g = process.to_grayscale(gradient_rgba)
    a = _arr1(process.dither(g, algo))
    assert set(np.unique(a).tolist()) <= {0, 255}
    assert abs(a.mean() / 255 - np.asarray(g).mean() / 255) < 0.08


def test_unknown_algo_raises(gradient_rgba):
    with pytest.raises(ValueError):
        process.dither(process.to_grayscale(gradient_rgba), "nope")
```

- [ ] **Step 2: Run — expect pass**

Run: `.venv/bin/pytest tests/test_process.py -k dither -v`  → passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_process.py
git commit -m "test: lock dither output semantics"
```

---

## Task 6: LDView render wrapper

**Files:** Create `brick_icons/render.py`. Test `tests/test_render.py`.

- [ ] **Step 1: Write `tests/test_render.py`**

```python
from pathlib import Path
import pytest
from PIL import Image
from brick_icons.config import load_config
from brick_icons import render


def test_resolve_part_id(tmp_path):
    (tmp_path / "vendor/ldraw/parts").mkdir(parents=True)
    (tmp_path / "vendor/ldraw/parts/3001.dat").write_text("0 brick")
    cfg = load_config(root=tmp_path)
    assert render.resolve_part(cfg, "3001") == tmp_path / "vendor/ldraw/parts/3001.dat"


def test_resolve_explicit_path(tmp_path):
    f = tmp_path / "c.ldr"; f.write_text("0")
    assert render.resolve_part(load_config(root=tmp_path), str(f)) == f


def test_resolve_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        render.resolve_part(load_config(root=tmp_path), "9999999")


def test_resolve_latlong_presets_and_explicit():
    assert render.resolve_latlong("iso") == (30.0, 45.0)
    assert render.resolve_latlong("top") == (90.0, 0.0)
    assert render.resolve_latlong("15,-60") == (15.0, -60.0)
    with pytest.raises(ValueError):
        render.resolve_latlong("sideways")


def test_build_argv_uses_launcher_prefix():
    direct = load_config(root=".", overrides={"ldview_launcher": []})
    argv = render.build_argv(direct, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert argv[0] == str(direct.ldview)            # no prefix on Linux/direct
    rosetta = load_config(root=".", overrides={"ldview_launcher": ["arch", "-x86_64"]})
    argv2 = render.build_argv(rosetta, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert argv2[:3] == ["arch", "-x86_64", str(rosetta.ldview)]


def test_build_argv_has_fidelity_lighting_angle():
    cfg = load_config(root=".")
    argv = render.build_argv(cfg, Path("/p/3001.dat"), Path("/o/3001.png"))
    assert str(cfg.ldview) in argv
    for flag in ["-SaveSnapshot=/o/3001.png", "-SaveWidth=2048", "-SaveHeight=2048",
                 "-AutoCrop=1", "-SaveAlpha=1", "-EdgeLines=1",
                 "-CurveQuality=12", "-HiResPrimitives=1", "-AllowPrimitiveSubstitution=1",
                 "-Lighting=1", "-UseQualityLighting=1", "-LightVector=-1,1,2",
                 "-DefaultLatLong=30.0,45.0", f"-LDrawDir={cfg.ldraw_dir}"]:
        assert flag in argv


def test_build_argv_part_color_optional():
    base = load_config(root=".")
    assert not any(a.startswith("-DefaultColor3") for a in
                   render.build_argv(base, Path("/p/x.dat"), Path("/o/x.png")))
    colored = load_config(root=".", overrides={"part_color": "0xCC0000"})
    assert "-DefaultColor3=0xCC0000" in render.build_argv(colored, Path("/p/x.dat"), Path("/o/x.png"))


LDVIEW = Path("vendor/LDView.app/Contents/MacOS/LDView")


@pytest.mark.skipif(not LDVIEW.exists(), reason="run scripts/setup-ldview.sh")
def test_render_part_live(tmp_path):
    cfg = load_config(root=Path.cwd())
    out = tmp_path / "3001.png"
    render.render_part(cfg, "3001", out)
    im = Image.open(out)
    assert im.mode == "RGBA" and im.width > 0
```

- [ ] **Step 2: Run — expect fail** (`No module named 'brick_icons.render'`)

- [ ] **Step 3: Write `brick_icons/render.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import Config

ANGLE_PRESETS = {
    "iso": (30.0, 45.0), "front": (0.0, 0.0), "back": (0.0, 180.0),
    "left": (0.0, -90.0), "right": (0.0, 90.0), "top": (90.0, 0.0),
    "bottom": (-90.0, 0.0),
}


def resolve_latlong(angle: str) -> tuple[float, float]:
    if angle in ANGLE_PRESETS:
        return ANGLE_PRESETS[angle]
    try:
        lat, long = (float(x) for x in angle.split(","))
        return lat, long
    except (ValueError, TypeError):
        raise ValueError(f"bad angle {angle!r}: preset {list(ANGLE_PRESETS)} or 'LAT,LONG'")


def resolve_part(cfg: Config, part: str) -> Path:
    p = Path(part)
    if p.suffix.lower() in (".dat", ".ldr", ".mpd") and p.exists():
        return p
    candidate = cfg.ldraw_dir / "parts" / f"{part}.dat"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"could not resolve part {part!r} (looked for {candidate})")


def build_argv(cfg: Config, part_file: Path, out_png: Path) -> list[str]:
    lat, long = resolve_latlong(cfg.angle)
    argv = [
        *cfg.ldview_launcher, str(cfg.ldview), str(part_file),
        f"-LDrawDir={cfg.ldraw_dir}",
        f"-SaveSnapshot={out_png}",
        f"-SaveWidth={cfg.render_px}", f"-SaveHeight={cfg.render_px}",
        "-AutoCrop=1", "-SaveAlpha=1", "-EdgeLines=1",
        f"-CurveQuality={cfg.curve_quality}",
        "-HiResPrimitives=1", "-AllowPrimitiveSubstitution=1",
        "-Lighting=1", "-UseQualityLighting=1", "-LightVector=-1,1,2",
        f"-DefaultLatLong={lat},{long}",
    ]
    if cfg.part_color:
        argv.append(f"-DefaultColor3={cfg.part_color}")
    return argv


def render_part(cfg: Config, part: str, out_png: Path) -> Path:
    part_file = resolve_part(cfg, part)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(build_argv(cfg, part_file, out_png), check=True, capture_output=True)
    if not out_png.exists():
        raise RuntimeError(f"LDView did not write {out_png}")
    return out_png
```

- [ ] **Step 4: Run — expect pass** (live test skips if LDView absent)

Run: `.venv/bin/pytest tests/test_render.py -v`

- [ ] **Step 5: Commit**

```bash
git add brick_icons/render.py tests/test_render.py
git commit -m "feat: LDView render wrapper (fidelity/lighting/angle/color argv)"
```

---

## Task 7: SVG vector output (potrace)

**Files:** Create `brick_icons/trace.py`. Test `tests/test_trace.py`.

- [ ] **Step 1: Write `tests/test_trace.py`**

```python
import re
import shutil
import numpy as np
import pytest
from PIL import Image
from brick_icons import trace, process

HAVE_POTRACE = shutil.which("potrace") is not None
pytestmark = pytest.mark.skipif(not HAVE_POTRACE, reason="potrace not installed")


def _disc():
    yy, xx = np.mgrid[0:120, 0:120]
    m = (xx - 60) ** 2 + (yy - 60) ** 2 <= 50 ** 2
    a = np.zeros((120, 120, 4), np.uint8)
    a[m, :3] = 110; a[m, 3] = 255
    return Image.fromarray(a, "RGBA")


def test_outline_svg_has_paths(tmp_path):
    out = tmp_path / "d.svg"
    trace.outline_svg(_disc(), out, interior=False)
    txt = out.read_text()
    assert "<svg" in txt and "<path" in txt
    assert 'transform="translate(' in txt   # potrace transform preserved


def test_cel_svg_layers_match_bands(tmp_path):
    out = tmp_path / "c.svg"
    # gradient disc so multiple bands exist
    yy, xx = np.mgrid[0:120, 0:120]
    m = (xx - 60) ** 2 + (yy - 60) ** 2 <= 50 ** 2
    a = np.zeros((120, 120, 4), np.uint8)
    a[..., 0] = a[..., 1] = a[..., 2] = np.clip(xx * 2, 0, 255)
    a[m, 3] = 255; a[~m, 3] = 0
    trace.cel_svg(Image.fromarray(a, "RGBA"), out, levels=4)
    txt = out.read_text()
    fills = set(re.findall(r'fill="(#[0-9a-f]{6})"', txt))
    assert len(fills) >= 2          # multiple tonal bands
    assert "<path" in txt


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick absent")
def test_outline_svg_rasterizes_nonblank(tmp_path):
    svg = tmp_path / "d.svg"; png = tmp_path / "d.png"
    trace.outline_svg(_disc(), svg, interior=True)
    import subprocess
    subprocess.run(["magick", "-density", "150", str(svg), "-background", "white",
                    "-flatten", str(png)], check=True, capture_output=True)
    assert (np.asarray(Image.open(png).convert("L")) < 250).sum() > 0
```

- [ ] **Step 2: Run — expect fail** (`No module named 'brick_icons.trace'`)

- [ ] **Step 3: Write `brick_icons/trace.py`**

```python
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import process

_VIEWBOX = re.compile(r'viewBox="([^"]+)"')
_TRANSFORM = re.compile(r'<g transform="([^"]+)"')
_PATH_D = re.compile(r'<path[^>]*\sd="([^"]+)"')


def _potrace(mask_L: Image.Image) -> tuple[list[str], str, str]:
    """Trace a 1-bit mask; return (path_d_list, viewbox, g_transform)."""
    with tempfile.TemporaryDirectory() as td:
        pbm = Path(td) / "m.pbm"
        svg = Path(td) / "m.svg"
        mask_L.convert("1").save(pbm)
        subprocess.run(["potrace", "-s", "-o", str(svg), str(pbm),
                        "--turdsize", "2", "--alphamax", "1.0", "--opttolerance", "0.2"],
                       check=True, capture_output=True)
        txt = svg.read_text()
    vb = _VIEWBOX.search(txt).group(1)
    tf_match = _TRANSFORM.search(txt)
    if not tf_match:
        return [], vb, ""          # empty mask -> no paths
    return _PATH_D.findall(txt), vb, tf_match.group(1)


def _write_svg(out_path: Path, viewbox: str, transform: str,
               layers: list[tuple[list[str], str]]) -> None:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
             f'preserveAspectRatio="xMidYMid meet">',
             '<rect width="100%" height="100%" fill="white"/>']
    if transform:
        parts.append(f'<g transform="{transform}" stroke="none">')
        for ds, fill in layers:
            for d in ds:
                parts.append(f'<path d="{d}" fill="{fill}"/>')
        parts.append("</g>")
    parts.append("</svg>")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts))


def outline_svg(rgba: Image.Image, out_path: Path, interior: bool = True) -> Path:
    line = process.make_outline(rgba.convert("RGBA"), interior=interior)
    ds, vb, tf = _potrace(line)
    _write_svg(Path(out_path), vb, tf, [(ds, "black")])
    return Path(out_path)


def cel_svg(rgba: Image.Image, out_path: Path, levels: int = 4) -> Path:
    rgba = rgba.convert("RGBA")
    g = process.posterize(process.to_grayscale(rgba), levels)
    arr = np.asarray(g)
    sil = np.asarray(process._silhouette_mask(rgba), int) > 16
    layers: list[tuple[list[str], str]] = []
    vb = tf = None
    for v in sorted(set(np.unique(arr).tolist())):
        if v >= 255:
            continue
        mask = (arr <= v) & sil          # cumulative: this dark or darker
        if mask.sum() == 0:
            continue
        mL = Image.fromarray(np.where(mask, 0, 255).astype(np.uint8), "L")
        ds, vbb, tff = _potrace(mL)
        if not ds:
            continue
        vb = vb or vbb
        tf = tf or tff
        layers.append((ds, f"#{v:02x}{v:02x}{v:02x}"))
    layers.reverse()                     # lightest/largest first, darker on top
    _write_svg(Path(out_path), vb or "0 0 1 1", tf or "", layers)
    return Path(out_path)
```

- [ ] **Step 4: Run — expect pass** (skips if potrace absent)

Run: `.venv/bin/pytest tests/test_trace.py -v`

- [ ] **Step 5: Commit**

```bash
git add brick_icons/trace.py tests/test_trace.py
git commit -m "feat: potrace SVG output (outline + stacked-band cel)"
```

---

## Task 8: CLI — format/mode/shading wiring + batch + debug

**Files:** Create `brick_icons/cli.py`. Test `tests/test_cli.py`.

- [ ] **Step 1: Write `tests/test_cli.py`**

```python
from pathlib import Path
import shutil
import numpy as np
import pytest
from PIL import Image
from brick_icons import cli


def _fake_render(monkeypatch, size=(400, 300)):
    def fake(cfg, part, out_png):
        out_png.parent.mkdir(parents=True, exist_ok=True)
        arr = np.zeros((size[1], size[0], 4), np.uint8)
        arr[40:-40, 40:-40, :3] = 90
        arr[40:-40, 40:-40, 3] = 255
        Image.fromarray(arr, "RGBA").save(out_png)
        return out_png
    monkeypatch.setattr(cli.render, "render_part", fake)


def test_png_both_writes_gray_and_mono(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    assert cli.main(["3001", "--mode", "both", "--out", str(tmp_path),
                     "--root", str(tmp_path)]) == 0
    assert (tmp_path / "3001.gray.png").exists()
    assert Image.open(tmp_path / "3001.mono.png").mode == "1"


def test_png_color_mode(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "color", "--out", str(tmp_path), "--root", str(tmp_path)])
    assert Image.open(tmp_path / "3001.color.png").mode == "RGB"


def test_mono_size(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--mode", "mono", "--width", "120", "--height", "80",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert Image.open(tmp_path / "3001.mono.png").size == (120, 80)


def test_cel_mono_posterizes(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--shading", "cel", "--mode", "gray",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    # cel gray should have few distinct levels
    levels = len(set(np.unique(Image.open(tmp_path / "3001.gray.png")).tolist()))
    assert levels <= 6


@pytest.mark.skipif(shutil.which("potrace") is None, reason="potrace absent")
def test_svg_outline(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    cli.main(["3001", "--format", "svg", "--shading", "outline",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert (tmp_path / "3001.svg").exists()
    assert "<path" in (tmp_path / "3001.svg").read_text()


def test_svg_requires_vector_shading(tmp_path, monkeypatch, capsys):
    _fake_render(monkeypatch)
    cli.main(["3001", "--format", "svg", "--shading", "normal",
              "--out", str(tmp_path), "--root", str(tmp_path)])
    assert not (tmp_path / "3001.svg").exists()
    assert "shading" in capsys.readouterr().out.lower()


def test_debug_dir_saves_stages(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    dbg = tmp_path / "dbg"
    cli.main(["3001", "--mode", "mono", "--out", str(tmp_path),
              "--root", str(tmp_path), "--debug-dir", str(dbg)])
    assert (dbg / "render" / "3001.png").exists()
    assert (dbg / "tone" / "3001.png").exists()
    assert (dbg / "mono" / "3001.png").exists()


def test_batch_list_file(tmp_path, monkeypatch):
    _fake_render(monkeypatch)
    lst = tmp_path / "p.txt"; lst.write_text("# bins\n3001\n3002\n\n")
    cli.main(["--list", str(lst), "--mode", "mono", "--out", str(tmp_path),
              "--root", str(tmp_path)])
    assert (tmp_path / "3001.mono.png").exists() and (tmp_path / "3002.mono.png").exists()
```

- [ ] **Step 2: Run — expect fail** (`No module named 'brick_icons.cli'`)

- [ ] **Step 3: Write `brick_icons/cli.py`**

```python
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

from . import render, process, trace
from .config import load_config, Config


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="brick-icons",
                                description="Render LEGO parts into bin-label assets.")
    p.add_argument("parts", nargs="*", help="part ids or .dat/.ldr paths")
    p.add_argument("--list", help="file with one part per line (overrides positional)")
    p.add_argument("--out", default="out")
    p.add_argument("--root", default=".")
    p.add_argument("--config", default=None)
    p.add_argument("--format", dest="fmt", choices=["png", "svg", "both"])
    p.add_argument("--mode", choices=["gray", "mono", "color", "both"])
    p.add_argument("--shading", choices=["normal", "cel", "outline"])
    p.add_argument("--cel-levels", type=int)
    p.add_argument("--outline-interior", dest="outline_interior", action="store_true", default=None)
    p.add_argument("--no-outline-interior", dest="outline_interior", action="store_false")
    p.add_argument("--dither", choices=["threshold", "floyd", "ordered", "atkinson"])
    p.add_argument("--angle")
    p.add_argument("--part-color")
    p.add_argument("--curve-quality", type=int)
    p.add_argument("--render-px", type=int)
    p.add_argument("--scale", type=float)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--dpi", type=int)
    p.add_argument("--label-mm", type=float, nargs=2, metavar=("W", "H"))
    p.add_argument("--margin", type=int)
    p.add_argument("--threshold", type=int)
    p.add_argument("--gamma", type=float)
    p.add_argument("--levels", type=int, nargs=2, metavar=("BLACK", "WHITE"))
    p.add_argument("--debug-dir", default=None)
    return p.parse_args(argv)


def _config_from_args(args) -> Config:
    toml = args.config or str(Path(args.root) / "labels.toml")
    overrides = {
        "fmt": args.fmt, "mode": args.mode, "shading": args.shading,
        "cel_levels": args.cel_levels, "outline_interior": args.outline_interior,
        "dither": args.dither, "angle": args.angle, "part_color": args.part_color,
        "curve_quality": args.curve_quality, "render_px": args.render_px,
        "scale": args.scale, "width": args.width, "height": args.height,
        "dpi": args.dpi, "label_mm": tuple(args.label_mm) if args.label_mm else None,
        "margin": args.margin, "threshold": args.threshold, "gamma": args.gamma,
        "levels": tuple(args.levels) if args.levels else None,
    }
    return load_config(toml_path=toml, overrides=overrides, root=args.root)


def _stage(debug_dir, stage, name) -> Path:
    d = Path(debug_dir) / stage
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{name}.png"


def _tone(cfg: Config, rgba: Image.Image) -> Image.Image:
    """The styled grayscale ('L') image per shading (normal/cel). Not for outline."""
    g = process.to_grayscale(rgba)
    if cfg.levels:
        g = process.apply_levels(g, cfg.levels[0], cfg.levels[1], cfg.gamma)
    elif cfg.gamma != 1.0:
        g = process.apply_levels(g, 0, 255, cfg.gamma)
    if cfg.shading == "cel":
        g = process.posterize(g, cfg.cel_levels)
    return g


def process_one(cfg: Config, part: str, out_dir: Path, debug_dir=None) -> None:
    name = Path(part).stem if Path(part).suffix else part
    render_png = (_stage(debug_dir, "render", name) if debug_dir
                  else out_dir / f"{name}.render.png")
    render.render_part(cfg, part, render_png)
    rgba = Image.open(render_png).convert("RGBA")
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- SVG ---
    if cfg.fmt in ("svg", "both"):
        if cfg.shading == "outline":
            trace.outline_svg(rgba, out_dir / f"{name}.svg", interior=cfg.outline_interior)
        elif cfg.shading == "cel":
            trace.cel_svg(rgba, out_dir / f"{name}.svg", levels=cfg.cel_levels)
        else:
            print(f"skip svg for {name}: --shading must be outline or cel (got {cfg.shading})")

    # --- PNG ---
    if cfg.fmt in ("png", "both"):
        if cfg.shading == "outline":
            tone = process.make_outline(rgba, interior=cfg.outline_interior)
        else:
            tone = _tone(cfg, rgba)
        if debug_dir:
            tone.save(_stage(debug_dir, "tone", name))

        if cfg.mode == "color":
            process.flatten_rgb(rgba).save(out_dir / f"{name}.color.png")
        if cfg.mode in ("gray", "both"):
            tone.save(out_dir / f"{name}.gray.png")
        if cfg.mode in ("mono", "both"):
            fitted = process.fit_contain(tone, cfg.width, cfg.height, cfg.margin, cfg.scale)
            if cfg.shading == "outline":
                mono = process.dither(fitted, "threshold", 200)  # keep lines crisp
            else:
                mono = process.dither(fitted, cfg.dither, cfg.threshold)
            if debug_dir:
                mono.save(_stage(debug_dir, "mono", name))
            mono.save(out_dir / f"{name}.mono.png")

    if not debug_dir and render_png.exists():
        render_png.unlink()


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

- [ ] **Step 4: Run — expect pass** (svg tests skip without potrace)

Run: `.venv/bin/pytest tests/test_cli.py -v`

- [ ] **Step 5: Commit**

```bash
git add brick_icons/cli.py tests/test_cli.py
git commit -m "feat: CLI wiring (format/mode/shading, batch, debug-dir)"
```

---

## Task 9: End-to-end live run, README, PROJECTS.md

**Files:** README expand; modify `~/src/PROJECTS.md`. No new source.

- [ ] **Step 1: Full live run (setup script already run)**

```bash
.venv/bin/python -m brick_icons.cli 3001 3941 \
  --format both --shading cel --mode both --out out --debug-dir debug --root .
.venv/bin/python -m brick_icons.cli 3001 --format svg --shading outline --out out --root .
ls out/ debug/*/
```
Expected: `out/3001.gray.png out/3001.mono.png out/3001.svg out/3941.*` and `debug/render|tone|mono/`.

- [ ] **Step 2: Eyeball + open results**

```bash
open out/3001.mono.png out/3001.svg out/3941.gray.png
```
Tune lighting/levels if needed (e.g. `--levels 40 200 --gamma 1.2`) and record good values in `labels.toml`.

- [ ] **Step 3: Run full suite**

Run: `.venv/bin/pytest -q`
Expected: all pass (live render + potrace tests pass if installed, else skip).

- [ ] **Step 4: Expand `README.md`**

```markdown
# brick-icons

Render LEGO parts from LDraw (via LDView) into monochrome/grayscale bitmaps and
SVGs for Brother P-touch (LBX) bin labels.

## Setup (macOS)

    python3 -m venv .venv && .venv/bin/pip install -e .
    ./scripts/setup-ldview.sh        # vendor/LDView.app + vendor/ldraw + potrace

LDView is x86_64-only on macOS; it runs under Rosetta automatically.

### Porting to Linux/Windows

Only the LDView invocation is platform-specific. Install LDView + potrace via your
package manager, then in `labels.toml` set `ldview = "/path/to/ldview"` and
`ldview_launcher = []`. No code changes needed; `setup-ldview.sh` is macOS-only.

## Usage

    # both PNG outputs, normal shading
    .venv/bin/python -m brick_icons.cli 3001 --mode both --out out

    # cel-shaded, 1-bit Atkinson dither, batch from a list, 360 dpi
    .venv/bin/python -m brick_icons.cli --list bins.txt --shading cel \
        --mode mono --dither atkinson --dpi 360 --out out

    # vector outline SVG, top-down
    .venv/bin/python -m brick_icons.cli 3001 --format svg --shading outline \
        --angle top --out out

    # size by physical tape
    .venv/bin/python -m brick_icons.cli 3001 --label-mm 24 12 --mode mono

Format: `png` | `svg` | `both`.  SVG needs `--shading outline` or `cel`.
Shading: `normal` | `cel` (`--cel-levels N`) | `outline` (`--no-outline-interior`).
Mode (PNG): `gray` | `mono` | `color` | `both`.
Dither: `threshold` | `floyd` | `ordered` | `atkinson`.
Angle: `iso` (default) | `front|back|left|right|top|bottom` | `LAT,LONG`.
Knobs: `--part-color 0xRRGGBB`, `--scale 0-1`, `--curve-quality`, `--render-px`,
`--levels B W`, `--gamma`, `--debug-dir DIR`.

See `docs/superpowers/specs/` for the design.
```

- [ ] **Step 5: Add to `~/src/PROJECTS.md`** under `## Personal`:

```
- **brick-icons** — Python CLI rendering LEGO parts from LDraw (LDView under Rosetta) into 1-bit dithered / grayscale / color PNGs and potrace SVGs (normal/cel/outline shading) for Brother P-touch (LBX) bin labels. Pure image+vector core, thin LDView wrapper.
```

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: usage README for brick-icons"
```

---

## Notes for the implementer

- **macOS only.** Render needs `arch -x86_64`, `hdiutil`, the LDView `.app`; SVG needs `potrace`. The pure `process`/`config` tests run anywhere; `render`/`trace`/svg-`cli` tests self-skip when their tool is absent.
- **Atkinson is O(W·H) in Python** — only ever runs on the fitted label image (≤ ~360px), never the 2048 render.
- **potrace transform** must be preserved when assembling SVGs (see `trace._write_svg`); dropping it renders paths off-canvas (a real bug hit during prototyping).
- **`_silhouette_mask`** is shared by `process.make_outline` and `trace.cel_svg`; keep it in `process`.
- **Tuning is expected** (Task 9 Step 2): defaults are validated-good, but `--levels`/`--gamma`/`--cel-levels` are the dials for per-part legibility.
```
