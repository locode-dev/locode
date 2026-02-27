#!/bin/bash
# scripts/patch-electron-icon.sh
# 
# Patches the local Electron.app icon so that during `npm run electron:dev`
# the Dock shows YOUR icon instead of the default Electron atom icon.
#
# This is a one-time setup for development. The DMG/packaged app always
# uses the correct icon — this only affects dev mode.
#
# Usage: bash scripts/patch-electron-icon.sh
# Safe to re-run: it backs up the original icon first.

set -e
cd "$(dirname "$0")/.."   # run from project root

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; BOLD="\033[1m"; RESET="\033[0m"
ok()   { echo -e "${GREEN}  ✅ $1${RESET}"; }
warn() { echo -e "${YELLOW}  ⚠  $1${RESET}"; }
fail() { echo -e "${RED}  ❌ $1${RESET}"; exit 1; }

echo -e "\n${BOLD}Patching Electron dev icon...${RESET}\n"

# ── Find your icon ─────────────────────────────────────────────────────────────
ICON_SRC=""
[ -f "assets/locode.icns" ] && ICON_SRC="assets/locode.icns"
[ -z "$ICON_SRC" ] && [ -f "assets/locode.png" ] && ICON_SRC="assets/locode.png"
[ -z "$ICON_SRC" ] && fail "No icon found at assets/locode.icns or assets/locode.png"

echo "  Using icon: $ICON_SRC"

# If we only have a .png, convert it to .icns first
if [[ "$ICON_SRC" == *.png ]]; then
    echo "  Converting PNG → ICNS..."
    TMPSET=$(mktemp -d)/locode.iconset
    mkdir -p "$TMPSET"
    sips -z 16  16  "$ICON_SRC" --out "$TMPSET/icon_16x16.png"     >/dev/null
    sips -z 32  32  "$ICON_SRC" --out "$TMPSET/icon_16x16@2x.png"  >/dev/null
    sips -z 32  32  "$ICON_SRC" --out "$TMPSET/icon_32x32.png"     >/dev/null
    sips -z 64  64  "$ICON_SRC" --out "$TMPSET/icon_32x32@2x.png"  >/dev/null
    sips -z 128 128 "$ICON_SRC" --out "$TMPSET/icon_128x128.png"   >/dev/null
    sips -z 256 256 "$ICON_SRC" --out "$TMPSET/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$ICON_SRC" --out "$TMPSET/icon_256x256.png"   >/dev/null
    sips -z 512 512 "$ICON_SRC" --out "$TMPSET/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$ICON_SRC" --out "$TMPSET/icon_512x512.png"   >/dev/null
    cp "$ICON_SRC" "$TMPSET/icon_512x512@2x.png"
    iconutil -c icns "$TMPSET" -o "assets/locode.icns"
    ICON_SRC="assets/locode.icns"
    ok "Created assets/locode.icns"
fi

# ── Find Electron.app in node_modules ─────────────────────────────────────────
ELECTRON_APP=""

# Standard npm location
for candidate in \
    "node_modules/electron/dist/Electron.app" \
    "node_modules/.pnpm/electron@*/node_modules/electron/dist/Electron.app"
do
    matches=$(ls -d $candidate 2>/dev/null | head -1)
    [ -n "$matches" ] && ELECTRON_APP="$matches" && break
done

[ -z "$ELECTRON_APP" ] && fail "Electron.app not found in node_modules. Run 'npm install' first."
echo "  Electron.app: $ELECTRON_APP"

ELECTRON_ICON_DIR="${ELECTRON_APP}/Contents/Resources"
ELECTRON_ICON="${ELECTRON_ICON_DIR}/electron.icns"

[ -d "$ELECTRON_ICON_DIR" ] || fail "Electron Resources dir not found: $ELECTRON_ICON_DIR"

# ── Back up original icon ──────────────────────────────────────────────────────
BACKUP="${ELECTRON_ICON_DIR}/electron.icns.original"
if [ ! -f "$BACKUP" ]; then
    cp "$ELECTRON_ICON" "$BACKUP"
    ok "Backed up original icon → electron.icns.original"
else
    ok "Original already backed up"
fi

# ── Patch the icon ─────────────────────────────────────────────────────────────
cp "$ICON_SRC" "$ELECTRON_ICON"
ok "Patched Electron.app icon with $ICON_SRC"

# ── Clear macOS icon cache (so Dock picks up the change) ──────────────────────
echo "  Clearing macOS icon cache..."
# Touch the app bundle to invalidate cache
touch "$ELECTRON_APP"
# Kill Dock to force reload (it will restart automatically)
killall Dock 2>/dev/null && echo "  Dock restarted" || echo "  (Dock restart not needed)"

echo ""
echo -e "${BOLD}${GREEN}Done!${RESET}"
echo "  The Electron dev icon is now patched."
echo "  Run: npm run electron:dev"
echo ""
echo -e "${YELLOW}  Note: If you run 'npm install' again, it will restore the original"
echo -e "  Electron icon. Just re-run this script to patch it again.${RESET}"
echo ""

# ── Restore helper ─────────────────────────────────────────────────────────────
cat << 'RESTORE_HINT'
  To restore the original Electron icon:
    cp node_modules/electron/dist/Electron.app/Contents/Resources/electron.icns.original \
       node_modules/electron/dist/Electron.app/Contents/Resources/electron.icns
RESTORE_HINT