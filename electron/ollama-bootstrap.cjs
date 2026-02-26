const fs = require("fs");
const os = require("os");
const path = require("path");
const https = require("https");
const http = require("http");
const { spawn, execSync } = require("child_process");

function exists(p) {
    try { fs.accessSync(p); return true; } catch { return false; }
}

function findOllamaBinary() {
    const candidates = [
        "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama",
        "/Applications/Ollama.app/Contents/MacOS/Ollama",
    ];
    return candidates.find(exists) || null;
}

function download(url, dest) {
    return new Promise((resolve, reject) => {
        const file = fs.createWriteStream(dest);
        https.get(url, (res) => {
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
        }).on("error", (err) => { file.close(); reject(err); });
    });
}

function openFile(filePath) {
    return new Promise((resolve, reject) => {
        const p = spawn("open", [filePath], { stdio: "ignore" });
        p.on("exit", (code) => (code === 0 ? resolve(true) : reject(new Error(`open failed ${code}`))));
    });
}

function isOllamaRunning() {
    return new Promise(resolve => {
        const req = http.get("http://127.0.0.1:11434/api/tags", { timeout: 2000 }, res => {
            resolve(res.statusCode < 500);
        });
        req.on("error", () => resolve(false));
        req.on("timeout", () => { req.destroy(); resolve(false); });
    });
}

function waitForOllama(timeoutMs = 30000) {
    return new Promise(async (resolve) => {
        const deadline = Date.now() + timeoutMs;
        while (Date.now() < deadline) {
            await new Promise(r => setTimeout(r, 1000));
            if (await isOllamaRunning()) {
                console.log("[ollama] ready on :11434");
                return resolve(true);
            }
        }
        console.warn("[ollama] timeout waiting for :11434 — continuing anyway");
        resolve(false);
    });
}

async function startOllama(ollamaBin) {
    if (await isOllamaRunning()) {
        console.log("[ollama] already running on :11434");
        return true;
    }

    // Strategy 1: if the CLI binary exists in PATH, use it directly
    const cliBin = ["/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"].find(exists);
    if (cliBin) {
        console.log(`[ollama] spawning CLI: ${cliBin} serve`);
        const p = spawn(cliBin, ["serve"], {
            stdio: "ignore",
            detached: true,
            env: { ...process.env, OLLAMA_HOST: "0.0.0.0:11434" }
        });
        p.unref();
        return waitForOllama(25000);
    }

    // Strategy 2: launch the .app via `open -a Ollama` (macOS app manages its own daemon)
    if (process.platform === "darwin" && exists("/Applications/Ollama.app")) {
        console.log("[ollama] launching via: open -a Ollama");
        try {
            execSync("open -a Ollama", { timeout: 5000 });
        } catch (e) {
            console.error("[ollama] open -a Ollama failed:", e.message);
        }
        return waitForOllama(30000);
    }

    // Strategy 3: fallback — spawn the .app binary directly but with a shell env
    if (ollamaBin) {
        console.log(`[ollama] spawning app binary: ${ollamaBin} serve`);
        const p = spawn(ollamaBin, ["serve"], {
            stdio: "ignore",
            detached: true,
            shell: true,
            env: { ...process.env, HOME: os.homedir(), OLLAMA_HOST: "0.0.0.0:11434" }
        });
        p.unref();
        return waitForOllama(25000);
    }

    console.warn("[ollama] no binary found to start");
    return false;
}

async function ensureOllamaInstalled() {
    const found = findOllamaBinary();
    if (found) return { status: "ready", ollamaBin: found };

    // Check if .app exists even if CLI binary doesn't
    if (process.platform === "darwin" && exists("/Applications/Ollama.app")) {
        return { status: "ready", ollamaBin: "/Applications/Ollama.app/Contents/MacOS/Ollama" };
    }

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
