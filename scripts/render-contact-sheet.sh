#!/bin/sh
# Render the census parts list (parts.txt) as labeled SVGs and montage them
# into a single contact-sheet PNG for eyeball review. Each cell carries the
# part id in small print (--part-label) so artifacts can be traced back to a
# part without counting grid cells.
#
# Usage: scripts/render-contact-sheet.sh [out-dir]   (default: out/contact-sheet)
# Needs: resvg, imagemagick (see scripts/external-deps.lock)
set -e
cd "$(dirname "$0")/.."
OUT="${1:-out/contact-sheet}"

.venv/bin/python -m brick_icons.cli --list parts.txt \
    --format svg --shading outline --shade-style flat3 \
    --part-label --out "$OUT"

for f in "$OUT"/*.svg; do
    resvg --background white --width 600 "$f" "${f%.svg}.png"
done
magick montage "$OUT"/*.png -tile 6x -geometry +8+8 -background white \
    "$OUT/contact-sheet.png"
echo "contact sheet: $OUT/contact-sheet.png"
