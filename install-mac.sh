#!/bin/bash
# Swipe4Rest installer for macOS.
#   curl -fsSL https://raw.githubusercontent.com/Vokanzaa/Swipe4Rest/main/install-mac.sh | bash
# Downloads the right build for this Mac from the latest GitHub release, installs it to
# /Applications and opens it. Files fetched by curl aren't marked "downloaded from the
# internet", so macOS doesn't show the "could not verify" warning. Read it first if you like —
# it's short.
set -euo pipefail

REPO="Vokanzaa/Swipe4Rest"
case "$(uname -m)" in
  arm64) ASSET="Swipe4Rest-mac-apple-silicon.dmg" ;;
  *)     ASSET="Swipe4Rest-mac-intel.dmg" ;;
esac
URL="https://github.com/$REPO/releases/latest/download/$ASSET"
TMP="$(mktemp -d)"
trap 'hdiutil detach "$TMP/mnt" -quiet 2>/dev/null || true; rm -rf "$TMP"' EXIT

echo "→ Downloading $ASSET"
curl -fL --progress-bar "$URL" -o "$TMP/Swipe4Rest.dmg"

echo "→ Installing to /Applications"
hdiutil attach "$TMP/Swipe4Rest.dmg" -mountpoint "$TMP/mnt" -nobrowse -quiet
osascript -e 'quit app "Swipe4Rest"' 2>/dev/null || true
pkill -x Swipe4Rest 2>/dev/null || true
DEST="/Applications/Swipe4Rest.app"
if [ -w /Applications ]; then
  rm -rf "$DEST"; ditto "$TMP/mnt/Swipe4Rest.app" "$DEST"
else
  sudo rm -rf "$DEST"; sudo ditto "$TMP/mnt/Swipe4Rest.app" "$DEST"
fi
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

echo "→ Opening Swipe4Rest (look for it in the menu bar)"
open "$DEST"
echo "✓ Done. Drag any file in Finder and press Option."
