#!/usr/bin/env bash
# Install LDView.app + LDraw library into ./vendor; verify potrace. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
VENDOR="$PWD/vendor"; mkdir -p "$VENDOR"

DMG_URL="https://github.com/tcobbs/ldview/releases/download/v4.7/LDView_4.7.dmg"
DMG_SHA256="100806f260cf7217f22dc6b461224d7fd2e05f6ca3cb236394a63103c6730cf7"
LDRAW_URL="https://library.ldraw.org/library/updates/complete.zip"

if [ ! -x "$VENDOR/LDView.app/Contents/MacOS/LDView" ]; then
  echo "Downloading LDView dmg..."
  curl -sL -o "$VENDOR/LDView.dmg" "$DMG_URL"
  GOT=$(shasum -a 256 "$VENDOR/LDView.dmg" | cut -d' ' -f1)
  if [ "$GOT" != "$DMG_SHA256" ]; then
    echo "LDView dmg sha256 mismatch: got $GOT, want $DMG_SHA256" >&2
    rm -f "$VENDOR/LDView.dmg"; exit 1
  fi
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
