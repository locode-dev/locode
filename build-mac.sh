#!/bin/bash
# =============================================================================
# build-mac.sh — Build Locode.dmg for macOS
# Usage: bash build-mac.sh
# =============================================================================
set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

step()  { echo -e "\n${BOLD}▶ $1${RESET}"; }
ok()    { echo -e "${GREEN}  ✅ $1${RESET}"; }
warn()  { echo -e "${YELLOW}  ⚠  $1${RESET}"; }
fail()  { echo -e "${RED}  ❌ $1${RESET}"; exit 1; }

echo -e "${BOLD}"
echo "  ╔════════════════════════════════════╗"
echo "  ║    Locode macOS DMG Builder        ║"
echo "  ╚════════════════════════════════════╝"
echo -e "${RESET}"

# ── 0. Preflight checks ───────────────────────────────────────────────────────
step "Preflight checks"

command -v python3  >/dev/null 2>&1 || fail "python3 not found. Install Python 3.10+"
command -v npm      >/dev/null 2>&1 || fail "npm not found. Install Node.js 18+"
command -v node     >/dev/null 2>&1 || fail "node not found. Install Node.js 18+"

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
NODE_VER=$(node -e "process.stdout.write(process.versions.node)")
echo "  Python: $PY_VER  |  Node: $NODE_VER"

# Check icons
[ -f "assets/locode.icns" ] || fail "Missing assets/locode.icns — create it with iconutil"
[ -f "assets/locode.png"  ] || warn  "Missing assets/locode.png (dock icon fallback)"

# Check UI
[ -f "electron/ui/index.html" ] || {
    warn "electron/ui/index.html not found — checking root ui/ ..."
    [ -f "ui/index.html" ] && {
        mkdir -p electron/ui
        cp -r ui/* electron/ui/
        ok "Copied ui/ → electron/ui/"
    } || fail "No UI found. Build your frontend first."
}

ok "Preflight passed"

# ── 1. Install Python deps ────────────────────────────────────────────────────
step "Installing Python dependencies"
pip3 install pyinstaller requests websockets watchdog playwright \
    --break-system-packages -q
ok "Python deps ready"

# ── 2. Install Node deps ──────────────────────────────────────────────────────
step "Installing Node dependencies"
npm install --silent
ok "Node deps ready"

# ── 3. Download bundled Node.js ───────────────────────────────────────────────
step "Preparing bundled Node.js"
if [ -f "vendor/node/bin/node" ]; then
    ok "Bundled Node.js already present ($(vendor/node/bin/node --version))"
else
    bash scripts/download-node-macos.sh
    ok "Bundled Node.js downloaded"
fi

# ── 4. Bundle Playwright Chromium ─────────────────────────────────────────────
step "Preparing bundled Playwright Chromium"
if ls vendor/ms-playwright/chromium-* 2>/dev/null | head -1 | grep -q chromium; then
    ok "Playwright Chromium already bundled"
else
    echo "  Downloading Chromium (this takes a few minutes)..."
    export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/vendor/ms-playwright"
    python3 -m playwright install chromium
    ok "Playwright Chromium bundled"
fi

# ── 5. Kill stale ports ───────────────────────────────────────────────────────
step "Clearing ports 7824 7825 5173"
lsof -ti :7824,7825,5173 | xargs kill -9 2>/dev/null || true
sleep 1
ok "Ports clear"

# ── 6. Build PyInstaller backend binary ──────────────────────────────────────
step "Building Python backend binary (PyInstaller)"
rm -rf build dist dist-backend __pycache__
python3 -m PyInstaller --clean locode-backend-mac.spec --noconfirm

# Verify output
[ -f "dist/locode-backend-v4" ] || fail "PyInstaller output not found at dist/locode-backend-v4"

mkdir -p dist-backend
cp dist/locode-backend-v4 dist-backend/locode-backend-v4
chmod +x dist-backend/locode-backend-v4

# Quick sanity check — binary should at least print something
BACKEND_TEST=$(timeout 3 dist-backend/locode-backend-v4 2>&1 | head -3 || true)
echo "  Binary test output: $BACKEND_TEST"
ok "Backend binary built: $(du -sh dist-backend/locode-backend-v4 | cut -f1)"

# ── 7. Build Electron DMG ─────────────────────────────────────────────────────
step "Building Electron DMG"
npx electron-builder --mac dmg

DMG=$(ls release/*.dmg 2>/dev/null | head -1)
[ -n "$DMG" ] || fail "DMG not found in release/"

DMG_SIZE=$(du -sh "$DMG" | cut -f1)
ok "DMG created: $DMG ($DMG_SIZE)"

# ── 8. Verify DMG ─────────────────────────────────────────────────────────────
step "Verifying DMG"
hdiutil verify "$DMG" >/dev/null 2>&1 && ok "DMG integrity OK" || warn "DMG verify failed (non-fatal)"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "  ╔════════════════════════════════════════════╗"
echo "  ║  ✅ Build complete!                         ║"
echo "  ╚════════════════════════════════════════════╝"
echo -e "${RESET}"
echo "  📦 DMG: $DMG"
echo "  📏 Size: $DMG_SIZE"
echo ""
echo "  To install: open '$DMG' and drag Locode to Applications"
echo ""