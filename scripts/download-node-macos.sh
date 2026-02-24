#!/usr/bin/env bash
set -euo pipefail

# Pick a Node version that’s stable for you
NODE_VERSION="${NODE_VERSION:-v20.11.1}"

ARCH="$(uname -m)"
if [[ "$ARCH" == "arm64" ]]; then
  NODE_DIST="node-${NODE_VERSION}-darwin-arm64"
else
  NODE_DIST="node-${NODE_VERSION}-darwin-x64"
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="${ROOT_DIR}/vendor/node"

echo "Downloading ${NODE_DIST}..."
TMP_DIR="$(mktemp -d)"
cd "$TMP_DIR"

URL="https://nodejs.org/dist/${NODE_VERSION}/${NODE_DIST}.tar.gz"
curl -L "$URL" -o node.tgz

echo "Extracting..."
tar -xzf node.tgz

echo "Installing into ${DEST_DIR}..."
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R "${NODE_DIST}/"* "$DEST_DIR/"

echo "Done."
echo "Node: $("${DEST_DIR}/bin/node" -v)"
echo "NPM : $("${DEST_DIR}/bin/npm" -v)"