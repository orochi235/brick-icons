# lego-bin-labels

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
    .venv/bin/python -m lego_bin_labels.cli 3001 --mode both --out out

    # cel-shaded, 1-bit Atkinson dither, batch from a list, 360 dpi
    .venv/bin/python -m lego_bin_labels.cli --list bins.txt --shading cel \
        --mode mono --dither atkinson --dpi 360 --out out

    # vector outline SVG, top-down
    .venv/bin/python -m lego_bin_labels.cli 3001 --format svg --shading outline \
        --angle top --out out

    # size by physical tape
    .venv/bin/python -m lego_bin_labels.cli 3001 --label-mm 24 12 --mode mono

Format: `png` | `svg` | `both`.  SVG needs `--shading outline` or `cel`.
Shading: `normal` | `cel` (`--cel-levels N`) | `outline` (`--no-outline-interior`).
Mode (PNG): `gray` | `mono` | `color` | `both`.
Dither: `threshold` | `floyd` | `ordered` | `atkinson`.
Angle: `iso` (default) | `front|back|left|right|top|bottom` | `LAT,LONG`.
Knobs: `--part-color 0xRRGGBB`, `--scale 0-1`, `--curve-quality`, `--render-px`,
`--levels B W`, `--gamma`, `--debug-dir DIR`.

## Notes

- `gray` output is saved at full render resolution — a high-res master for the
  driver to scale and dither downstream. Only `mono` is fit to the label pixel
  size (`--width`/`--height` or `--label-mm`).
- `--mode color` emits the raw flattened color render and ignores `--shading`
  (color is a preview only; the printer is 1-bit).

See `docs/superpowers/specs/` for the design.
