// electron/ollama-bootstrap.cjs
// Handles Ollama detection, download prompt, and startup for both macOS and Windows.

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const { spawn, execSync } = require("child_process");

function exists(p) {
    try { fs.accessSync(p); return true; } catch { return false; }
}

// ── Platform detection ────────────────────────────────────────────────────────

const IS_MAC = process.platform === "darwin";
const IS_WIN = process.platform === "win32";

// ── Binary search ─────────────────────────────────────────────────────────────

function findOllamaBinary() {
    if (IS_MAC) {
        const candidates = [
            "/usr/local/bin/ollama",
            "/opt/homebrew/bin/ollama",
            "/Applications/Ollama.app/Contents/MacOS/Ollama",
        ];
        return candidates.find(exists) || null;
    }

    if (IS_WIN) {
        const candidates = [
            path.join(process.env.LOCALAPPDATA || "", "Programs", "Ollama", "ollama.exe"),
            path.join(process.env.ProgramFiles || "", "Ollama", "ollama.exe"),
            path.join(process.env.USERPROFILE || "", "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
            "C:\\Program Files\\Ollama\\ollama.exe",
        ];
        return candidates.find(exists) || _winWhere("ollama.exe");
    }

    // Linux fallback
    return _linuxWhich("ollama");
}

function _winWhere(bin) {
    try {
        const p = execSync(`where ${bin}`, { timeout: 3000, stdio: "pipe" })
            .toString().trim().split("\n")[0].trim();
        return p && exists(p) ? p : null;
    } catch { return null; }
}

function _linuxWhich(bin) {
    try {
        const p = execSync(`which ${bin}`, { timeout: 3000, stdio: "pipe" }).toString().trim();
        return p && exists(p) ? p : null;
    } catch { return null; }
}

// ── Server check ──────────────────────────────────────────────────────────────

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
    return new Promise(async resolve => {
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

// ── Start Ollama ──────────────────────────────────────────────────────────────

async function startOllama(ollamaBin) {
    if (await isOllamaRunning()) {
        console.log("[ollama] already running on :11434");
        return true;
    }

    if (IS_MAC) {
        // Try CLI binary first
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

        // Launch .app
        if (exists("/Applications/Ollama.app")) {
            console.log("[ollama] launching via: open -a Ollama");
            try { execSync("open -a Ollama", { timeout: 5000 }); } catch (e) {
                console.error("[ollama] open -a Ollama failed:", e.message);
            }
            return waitForOllama(30000);
        }
    }

    if (IS_WIN) {
        if (ollamaBin && exists(ollamaBin)) {
            console.log(`[ollama] spawning: ${ollamaBin} serve`);
            const p = spawn(ollamaBin, ["serve"], {
                stdio: "ignore",
                detached: true,
                shell: false,
                env: { ...process.env, OLLAMA_HOST: "127.0.0.1:11434" }
            });
            p.unref();
            return waitForOllama(30000);
        }

        // Try starting via Start Menu shortcut / app
        try {
            const appPath = path.join(
                process.env.LOCALAPPDATA || "", "Programs", "Ollama", "Ollama.exe"
            );
            if (exists(appPath)) {
                console.log(`[ollama] launching app: ${appPath}`);
                const p = spawn(appPath, [], { stdio: "ignore", detached: true, shell: false });
                p.unref();
                return waitForOllama(35000);
            }
        } catch (e) {
            console.warn("[ollama] Windows app launch failed:", e.message);
        }
    }

    // Generic fallback
    if (ollamaBin) {
        console.log(`[ollama] spawning binary: ${ollamaBin} serve`);
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

// ── Ensure installed ──────────────────────────────────────────────────────────

async function ensureOllamaInstalled() {
    const found = findOllamaBinary();
    if (found) return { status: "ready", ollamaBin: found };

    if (IS_MAC && exists("/Applications/Ollama.app")) {
        return { status: "ready", ollamaBin: "/Applications/Ollama.app/Contents/MacOS/Ollama" };
    }

    if (IS_WIN) {
        // Check common install locations one more time
        const appExe = path.join(
            process.env.LOCALAPPDATA || "", "Programs", "Ollama", "Ollama.exe"
        );
        if (exists(appExe)) {
            return { status: "ready", ollamaBin: appExe };
        }
    }

    // Not found — tell main.cjs to prompt the user
    return { status: "needs-install" };
}

module.exports = { ensureOllamaInstalled, findOllamaBinary, startOllama };
