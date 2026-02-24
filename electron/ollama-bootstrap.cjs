const fs = require("fs");
const os = require("os");
const path = require("path");
const https = require("https");
const { spawn } = require("child_process");

function exists(p) {
    try { fs.accessSync(p); return true; } catch { return false; }
}

function findOllamaBinary() {
    // Most common install paths
    const candidates = [
        "/Applications/Ollama.app/Contents/MacOS/Ollama",
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama"
    ];
    return candidates.find(exists) || null;
}

function download(url, dest) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(dest);
        https.get(url, (res) => {
            // follow redirects
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                file.close();
                return resolve(download(res.headers.location, dest));
            }
            if (res.statusCode !== 200) {
                file.close();
                return reject(new Error(`Download failed: ${res.statusCode}`));
            }
            res.pipe(file);
            file.on("finish", () => file.close(resolve));
        }).on("error", (err) => {
            file.close();
            reject(err);
        });
    });
}

function openFile(filePath) {
    // macOS open command opens DMG/Finder
    return new Promise((resolve, reject) => {
        const p = spawn("open", [filePath], { stdio: "ignore" });
        p.on("exit", (code) => (code === 0 ? resolve(true) : reject(new Error(`open failed ${code}`))));
    });
}

function startOllama(ollamaBin) {
    // Start server in background (Ollama app manages its own daemon)
    // For .app binary: `Ollama serve`
    return new Promise((resolve) => {
        const p = spawn(ollamaBin, ["serve"], { stdio: "ignore", detached: true });
        p.unref();
        resolve(true);
    });
}

/**
 * Ensures Ollama is installed; if not, downloads DMG and opens it for user install.
 * Returns:
 *  - { status: "ready", ollamaBin }
 *  - { status: "needs-install", dmgPath }
 */
async function ensureOllamaInstalled() {
    const found = findOllamaBinary();
    if (found) return { status: "ready", ollamaBin: found };

    // Official download endpoint (redirects to latest)
    // This is the stable “landing” url Ollama uses for mac downloads.
    const url = "https://ollama.com/download/mac";

    const dmgPath = path.join(os.tmpdir(), "Ollama.dmg");
    await download(url, dmgPath);
    await openFile(dmgPath);

    return { status: "needs-install", dmgPath };
}

module.exports = {
    ensureOllamaInstalled,
    findOllamaBinary,
    startOllama
};