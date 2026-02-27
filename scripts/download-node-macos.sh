#!/bin/bash
# scripts/download-node-macos.sh
# Downloads a standalone Node.js binary into vendor/node/
# This is bundled inside the .app so users don't need Node installed.

set -e

NODE_VERSION="20.18.1"
ARCH=$(uname -m)

if [ "$ARCH" = "arm64" ]; then
    NODE_ARCH="arm64"
else
    NODE_ARCH="x64"
fi

NODE_TARBALL="node-v${NODE_VERSION}-darwin-${NODE_ARCH}.tar.gz"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"
VENDOR_DIR="$(cd "$(dirname "$0")/.." && pwd)/vendor"
NODE_DIR="${VENDOR_DIR}/node"

echo "📦 Downloading Node.js v${NODE_VERSION} (${NODE_ARCH}) for macOS..."
echo "   URL: ${NODE_URL}"

mkdir -p "${VENDOR_DIR}"
TMP_DIR=$(mktemp -d)

curl -L --progress-bar "${NODE_URL}" -o "${TMP_DIR}/${NODE_TARBALL}"
echo "✅ Downloaded"

echo "📂 Extracting..."
tar -xzf "${TMP_DIR}/${NODE_TARBALL}" -C "${TMP_DIR}"

EXTRACTED="${TMP_DIR}/node-v${NODE_VERSION}-darwin-${NODE_ARCH}"
rm -rf "${NODE_DIR}"
mv "${EXTRACTED}" "${NODE_DIR}"

chmod +x "${NODE_DIR}/bin/node"
chmod +x "${NODE_DIR}/bin/npm"
chmod +x "${NODE_DIR}/bin/npx"

# Remove docs/man to reduce size (~30MB saved)
rm -rf "${NODE_DIR}/share"
rm -rf "${NODE_DIR}/include"

rm -rf "${TMP_DIR}"

echo ""
echo "✅ Node.js ready at: vendor/node/"
echo "   node: $(${NODE_DIR}/bin/node --version)"
echo "   npm:  $(${NODE_DIR}/bin/npm --version)"
echo "   Size: $(du -sh ${NODE_DIR} | cut -f1)"