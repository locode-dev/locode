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

# ── Check icons ───────────────────────────────────────────────────────────────
[ -f "assets/locode.icns" ] || fail "Missing assets/locode.icns — create it with iconutil"
[ -f "assets/locode.png"  ] || warn  "Missing assets/locode.png (dock icon fallback)"

# ── Ensure electron/ folder exists ───────────────────────────────────────────
mkdir -p electron

# ── FIX: Sync Electron HTML/JS files into electron/ ─────────────────────────
# main.cjs loads splash.html/setup.html/preload.cjs relative to __dirname
# which resolves to the electron/ folder inside the .app bundle.
# These files must live in electron/ BEFORE electron-builder runs.
step "Syncing Electron support files into electron/"

for f in splash.html setup.html; do
    if [ -f "$f" ]; then
        cp "$f" "electron/$f"
        ok "Copied $f → electron/$f"
    elif [ ! -f "electron/$f" ]; then
        fail "Missing $f (checked root and electron/) — cannot continue"
    else
        ok "electron/$f already present"
    fi
done

for f in preload.cjs preload.js ollama-bootstrap.cjs; do
    if [ -f "$f" ] && [ ! -f "electron/$f" ]; then
        cp "$f" "electron/$f"
        ok "Copied $f → electron/$f"
    elif [ -f "electron/$f" ]; then
        ok "electron/$f already present"
    fi
done

# ── FIX: Ensure ui/index.html exists at root ui/ (for PyInstaller spec) ─────
# PyInstaller spec bundles ("ui", "ui") → _MEIPASS/ui/
# server.py serves from UI_DIR = _MEIPASS/ui/
# So index.html MUST be at ui/index.html, not at root.
step "Ensuring ui/index.html exists for PyInstaller"

if [ -f "ui/index.html" ]; then
    ok "ui/index.html already present"
elif [ -f "index.html" ]; then
    mkdir -p ui
    cp index.html ui/index.html
    ok "Copied index.html → ui/index.html"
else
    fail "No index.html found (checked ui/index.html and index.html)"
fi

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
    [ -f "scripts/download-node-macos.sh" ] || fail "Missing scripts/download-node-macos.sh"
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

# Wipe EVERYTHING PyInstaller and Python might cache.
# Stale .pyc files mean changed source (server.py, builder.py etc.)
# gets packed as OLD bytecode — your edits never make it into the DMG.
rm -rf build dist dist-backend __pycache__
# Clear bytecode from agents/ and root — PyInstaller reads .pyc preferentially
find . -name "*.pyc" -not -path "*/node_modules/*" -delete 2>/dev/null || true
find . -name "__pycache__" -not -path "*/node_modules/*" -exec rm -rf {} + 2>/dev/null || true
ok "Cleared all Python bytecode caches"

[ -f "locode-backend-mac.spec" ] || fail "Missing locode-backend-mac.spec"

# --clean forces full re-analysis (ignores any surviving .toc cache)
# --noconfirm overwrites dist/ without prompting
python3 -m PyInstaller --clean locode-backend-mac.spec --noconfirm

# Verify output
[ -f "dist/locode-backend-v4" ] || fail "PyInstaller output not found at dist/locode-backend-v4"

mkdir -p dist-backend
cp dist/locode-backend-v4 dist-backend/locode-backend-v4
chmod +x dist-backend/locode-backend-v4

ok "Backend binary built: $(du -sh dist-backend/locode-backend-v4 | cut -f1)"

# ── 6b. Verify binary can start ───────────────────────────────────────────────
step "Smoke-testing backend binary"
# Give it 3s — it will start, print DEBUG lines, then begin serving
# We just want to confirm it doesn't crash immediately
# macOS has no GNU timeout — use gtimeout (brew coreutils) or perl fallback
if command -v gtimeout >/dev/null 2>&1; then
    BACKEND_OUT=$(gtimeout 3 dist-backend/locode-backend-v4 2>&1 || true)
else
    # Pure bash timeout: run in background, sleep, kill
    dist-backend/locode-backend-v4 >/tmp/_locode_test.txt 2>&1 &
    BG_PID=$!
    sleep 3
    kill $BG_PID 2>/dev/null || true
    BACKEND_OUT=$(cat /tmp/_locode_test.txt 2>/dev/null || true)
fi
echo "  Output: $(echo "$BACKEND_OUT" | head -3)"

if echo "$BACKEND_OUT" | grep -q "Traceback\|ModuleNotFoundError\|ImportError"; then
    fail "Backend binary crashed on startup — check PyInstaller spec hiddenimports"
fi
ok "Backend binary starts cleanly"

# ── 7. Build Electron DMG ─────────────────────────────────────────────────────
step "Building Electron DMG"
# Clean previous DMG outputs (electron-builder uses dist/ or release/)
rm -rf release
rm -f dist/*.dmg dist/*.dmg.blockmap

npx electron-builder --mac dmg

# electron-builder defaults to dist/ — check both dist/ and release/
DMG=$(ls dist/*.dmg 2>/dev/null | head -1)
[ -n "$DMG" ] || DMG=$(ls release/*.dmg 2>/dev/null | head -1)
[ -n "$DMG" ] || fail "DMG not found in dist/ or release/"

DMG_SIZE=$(du -sh "$DMG" | cut -f1)
ok "DMG created: $DMG ($DMG_SIZE)"

# ── 8. Verify DMG structure ───────────────────────────────────────────────────
step "Verifying DMG"
hdiutil verify "$DMG" >/dev/null 2>&1 && ok "DMG integrity OK" || warn "DMG verify failed (non-fatal)"

# Mount and check key files exist inside the bundle
MOUNT_DIR=$(mktemp -d)
hdiutil attach "$DMG" -mountpoint "$MOUNT_DIR" -nobrowse -quiet 2>/dev/null || {
    warn "Could not mount DMG to inspect — skipping bundle check"
    rmdir "$MOUNT_DIR" 2>/dev/null
}

if [ -d "$MOUNT_DIR/Locode.app" ]; then
    RES="$MOUNT_DIR/Locode.app/Contents/Resources"
    ok "Mounted at $MOUNT_DIR"
    echo "  Checking bundle contents..."

    check_path() {
        if [ -e "$RES/$1" ]; then
            echo -e "${GREEN}    ✅ $1${RESET}"
        else
            echo -e "${RED}    ❌ MISSING: $1${RESET}"
        fi
    }

    check_path "backend/locode-backend-v4"
    check_path "node/bin/node"
    check_path "ms-playwright"
    check_path "ui/index.html"
    check_path "locode.png"

    hdiutil detach "$MOUNT_DIR" -quiet 2>/dev/null || true
fi
rmdir "$MOUNT_DIR" 2>/dev/null || true

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