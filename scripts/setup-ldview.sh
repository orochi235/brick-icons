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
