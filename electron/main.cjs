// electron/main.cjs
"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell, Menu, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");
const { spawn } = require("child_process");

const { ensureOllamaInstalled, findOllamaBinary, startOllama } = require("./ollama-bootstrap.cjs");

// -------------------------
// Globals
// -------------------------
let backendProc = null;
let splashWin = null;
let setupWin = null;
let mainWin = null;

// -------------------------
// Helpers
// -------------------------
function isPackaged() {
    return app.isPackaged;
}

function getResourcesPath() {
    return process.resourcesPath;
}


function backendPath() {
    if (app.isPackaged) return path.join(process.resourcesPath, "backend", "locode-backend-v4");
    return path.join(__dirname, "..", "server.py");
}

function nodeBinDir() {
    // If you bundle node/npm into app resources, keep it here:
    // Contents/Resources/node/bin/node + npm
    if (isPackaged()) return path.join(getResourcesPath(), "node", "bin");
    return "";
}


function nodePath() {
    // packaged: /Applications/Locode.app/Contents/Resources/node/bin/node
    if (app.isPackaged) return path.join(process.resourcesPath, "node", "bin", "node");
    return process.env.LOCODE_NODE || process.env.NODE || "node";
}

function npmPath() {
    if (isPackaged()) return path.join(getResourcesPath(), "node", "bin", "npm");
    return process.env.LOCODE_NPM || process.env.NPM || "npm";
}

function playwrightBrowsersPath() {
    // packaged: /Applications/Locode.app/Contents/Resources/ms-playwright
    if (app.isPackaged) return path.join(process.resourcesPath, "ms-playwright");
    // dev: whatever you use locally
    return path.join(__dirname, "..", "vendor", "ms-playwright");
}

function waitForPort(port, host = "127.0.0.1", timeoutMs = 60000) {
    const start = Date.now();

    return new Promise((resolve, reject) => {
        const tryConnect = () => {
            const socket = net.createConnection(port, host);

            socket.once("connect", () => {
                socket.destroy();
                resolve(true);
            });

            socket.once("error", () => {
                socket.destroy();
                if (Date.now() - start > timeoutMs) {
                    reject(new Error(`Timed out waiting for ${host}:${port}`));
                } else {
                    setTimeout(tryConnect, 300);
                }
            });
        };

        tryConnect();
    });
}

function killPortsMac(ports = [5173, 7824, 7825]) {
    if (process.platform !== "darwin") return;
    try {
        // best-effort cleanup; ignore errors
        spawn("bash", ["-lc", `lsof -ti :${ports.join(",")} | xargs kill -9 || true`], { stdio: "ignore" });
    } catch (_) { }
}

// Optional: unload all models quickly on quit (does NOT stop Ollama daemon, just unloads VRAM)
function unloadOllamaModelsBestEffort() {
    try {
        const curl = spawn("bash", ["-lc", `curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null 2>&1 || true; curl -s http://127.0.0.1:11434/api/generate -d '{"model":"qwen2.5-coder:14b","keep_alive":0}' >/dev/null 2>&1 || true`], { stdio: "ignore" });
        curl.on("error", () => { });
    } catch (_) { }
}

function createSplash() {
    splashWin = new BrowserWindow({
        width: 560,
        height: 500,
        resizable: false,
        frame: false,
        backgroundColor: "#0b0f19",
        icon: path.join(__dirname, "..", "assets", "locode.icns"),
        webPreferences: {
            contextIsolation: true,
            preload: fs.existsSync(path.join(__dirname, "preload.cjs"))
                ? path.join(__dirname, "preload.cjs")
                : path.join(__dirname, "preload.js"),
        },
    });
    splashWin.loadFile(path.join(__dirname, "splash.html"));
}

function createSetupWindow() {
    setupWin = new BrowserWindow({
        width: 560,
        height: 500,
        resizable: false,
        frame: false,
        backgroundColor: "#080b12",
        webPreferences: {
            contextIsolation: true,
            preload: fs.existsSync(path.join(__dirname, "preload.cjs"))
                ? path.join(__dirname, "preload.cjs")
                : path.join(__dirname, "preload.js"),
        },
    });
    setupWin.loadFile(path.join(__dirname, "setup.html"));
}

function createMainWindow() {
    mainWin = new BrowserWindow({
        title: "Locode — Local AI App Builder",
        width: 1280,
        height: 820,
        show: false,
        icon: path.join(__dirname, "..", "assets", "locode.icns"),
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            preload: fs.existsSync(path.join(__dirname, "preload.cjs"))
                ? path.join(__dirname, "preload.cjs")
                : path.join(__dirname, "preload.js"),
        },
    });

    mainWin.on("ready-to-show", () => {
        mainWin.show();
        if (splashWin && !splashWin.isDestroyed()) splashWin.close();
        if (setupWin && !setupWin.isDestroyed()) setupWin.close();
    });

    return mainWin;
}

function sendSetup(msg) {
    try {
        if (setupWin && !setupWin.isDestroyed()) setupWin.webContents.send("setup", msg);
    } catch (_) { }
}
function sendStatus(msg) {
    try {
        if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("status", msg);
    } catch (_) { }
}
function sendLog(line) {
    try {
        if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("log", line);
        if (setupWin && !setupWin.isDestroyed()) setupWin.webContents.send("log", line);
    } catch (_) { }
}

// -------------------------
// Backend spawn
// -------------------------
function startBackend(extraEnv = {}) {
    // Writable data dir — where projects and logs are stored
    // Must be outside the .app bundle (which is read-only)
    const locodeData = app.isPackaged
        ? path.join(app.getPath("userData"))   // ~/Library/Application Support/Locode
        : path.join(__dirname, "..");           // dev: project root

    const env = {
        ...process.env,
        LOCODE_NODE: nodePath(),
        LOCODE_NPM: app.isPackaged
            ? path.join(process.resourcesPath, "node", "bin", "npm")
            : (process.env.LOCODE_NPM || process.env.NPM || "npm"),

        // Writable path for projects + logs (avoids read-only _MEIPASS)
        LOCODE_DATA: locodeData,

        // ✅ Playwright: force bundled browsers + node
        PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath(),
        PLAYWRIGHT_NODEJS_PATH: nodePath(),
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",

        ...extraEnv,
    };

    if (app.isPackaged) {
        const backendExe = path.join(process.resourcesPath, "backend", "locode-backend-v4");
        backendProc = spawn(backendExe, [], { env, stdio: "pipe" });
    } else {
        backendProc = spawn("python3", [path.join(__dirname, "..", "server.py")], { env, stdio: "pipe" });
    }

    backendProc.stdout.on("data", d => console.log("[backend]", d.toString()));
    backendProc.stderr.on("data", d => console.error("[backend]", d.toString()));
}

// -------------------------
// First-run detection
// -------------------------
const FIRST_RUN_FLAG = path.join(app.getPath("userData"), ".locode-initialized");
function isFirstRun() {
    return !fs.existsSync(FIRST_RUN_FLAG);
}
function markInitialized() {
    try {
        fs.writeFileSync(FIRST_RUN_FLAG, new Date().toISOString());
    } catch (_) { }
}

// -------------------------
// IPC: folder picker (upload)
// -------------------------
ipcMain.handle("choose-folder", async () => {
    const win = mainWin || BrowserWindow.getFocusedWindow();
    const result = await dialog.showOpenDialog(win, {
        properties: ["openDirectory"],
        title: "Select your React project folder",
        buttonLabel: "Import Project",
    });
    if (result.canceled || !result.filePaths.length) return null;

    const folderPath = result.filePaths[0];
    const folderName = path.basename(folderPath);

    const files = {};
    const allowedExts = new Set([".jsx", ".tsx", ".js", ".ts", ".css", ".html", ".json", ".md", ".svg"]);
    const skipDirs = new Set(["node_modules", ".git", "dist", "build", ".next", "out", ".cache", ".turbo"]);

    function walkDir(dir, base) {
        let entries;
        try {
            entries = fs.readdirSync(dir, { withFileTypes: true });
        } catch (_) {
            return;
        }
        for (const entry of entries) {
            if (skipDirs.has(entry.name)) continue;
            const fullPath = path.join(dir, entry.name);
            const relPath = base ? `${base}/${entry.name}` : entry.name;
            if (entry.isDirectory()) walkDir(fullPath, relPath);
            else {
                const ext = path.extname(entry.name).toLowerCase();
                if (allowedExts.has(ext)) {
                    try {
                        const content = fs.readFileSync(fullPath, "utf8");
                        if (content.length < 500_000) files[relPath] = content;
                    } catch (_) { }
                }
            }
        }
    }

    walkDir(folderPath, "");
    return { name: folderName, path: folderPath, files, fileCount: Object.keys(files).length };
});

ipcMain.handle("open-external", async (_, url) => {
    await shell.openExternal(url);
});

// -------------------------
// Menu
// -------------------------
function setupMenu() {
    const template = [
        {
            label: app.name,
            submenu: [
                { role: "about" },
                { type: "separator" },
                { role: "services" },
                { type: "separator" },
                { role: "hide" },
                { role: "hideOthers" },
                { role: "unhide" },
                { type: "separator" },
                { role: "quit" },
            ],
        },
        { role: "editMenu" },
        { role: "viewMenu" },
        { role: "windowMenu" },
    ];
    Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// -------------------------
// Boot flows
// -------------------------
async function runFirstTimeSetup() {
    createSetupWindow();
    createMainWindow();
    await new Promise((r) => setTimeout(r, 700));

    // 1) Ensure Ollama exists
    sendSetup({ type: "step", step: "ollama", status: "active", label: "Checking Ollama…" });
    const res = await ensureOllamaInstalled();
    if (res.status === "needs-install") {
        sendSetup({ type: "step", step: "ollama", status: "error", label: "Ollama not found" });
        const choice = await dialog.showMessageBox(setupWin, {
            type: "info",
            buttons: ["Open Download Page", "Cancel"],
            title: "Install Ollama",
            message: "Ollama is required to run Locode.",
            detail: "1) Download and install Ollama from ollama.com\n2) Launch Ollama\n3) Re-open Locode",
        });
        if (choice.response === 0) shell.openExternal("https://ollama.com/download");
        app.quit();
        return;
    }
    sendSetup({ type: "step", step: "ollama", status: "done", label: "Ollama found ✓" });

    // 2) Start Ollama server (best-effort)
    sendSetup({ type: "step", step: "ollama-server", status: "active", label: "Starting Ollama server…" });
    const ollamaBin = findOllamaBinary();
    if (ollamaBin) await startOllama(ollamaBin);
    sendSetup({ type: "step", step: "ollama-server", status: "done", label: "Ollama server running ✓" });

    // 3) Start backend
    sendSetup({ type: "step", step: "backend", status: "active", label: "Starting backend…" });
    startBackend();

    // 4) Wait for HTTP UI
    sendSetup({ type: "step", step: "ui", status: "active", label: "Connecting…" });
    await waitForPort(7824, "127.0.0.1", 60000);

    sendSetup({ type: "step", step: "backend", status: "done", label: "Backend ready ✓" });
    sendSetup({ type: "step", step: "ui", status: "done", label: "All services ready ✓" });

    markInitialized();
    await mainWin.loadURL(`http://127.0.0.1:7824/?cb=${Date.now()}`);
}

async function boot() {
    createSplash();
    createMainWindow();

    sendStatus("Checking Ollama…");
    const res = await ensureOllamaInstalled();
    if (res.status === "needs-install") {
        await dialog.showMessageBox({
            type: "info",
            buttons: ["OK"],
            title: "Install Ollama",
            message: "Ollama is required to run Locode.",
            detail: "1) Download and install Ollama\n2) Launch Ollama once\n3) Re-open Locode",
        });
        app.quit();
        return;
    }

    sendStatus("Starting services…");
    const ollamaBin = findOllamaBinary();
    if (ollamaBin) await startOllama(ollamaBin);

    startBackend();

    sendStatus("Connecting to Locode UI…");
    await waitForPort(7824, "127.0.0.1", 60000);

    sendStatus("Loading app…");
    await mainWin.loadURL(`http://127.0.0.1:7824/?cb=${Date.now()}`);
}

// -------------------------
// App lifecycle
// -------------------------
app.whenReady().then(async () => {
    setupMenu();

    // mac dock icon — use resourcesPath in packaged mode (assets not in asar)
    if (process.platform === "darwin") {
        const iconPath = app.isPackaged
            ? path.join(process.resourcesPath, "locode.png")
            : path.join(__dirname, "..", "assets", "locode.png");
        const image = nativeImage.createFromPath(iconPath);
        if (!image.isEmpty()) app.dock.setIcon(image);
    }

    const startFn = isFirstRun() ? runFirstTimeSetup : boot;
    try {
        await startFn();
    } catch (e) {
        console.error(e);
        await dialog.showMessageBox({
            type: "error",
            title: "Locode failed to start",
            message: "Startup failed",
            detail: e?.stack || e?.message || String(e),
        });
        app.quit();
    }

    app.on("activate", async () => {
        if (BrowserWindow.getAllWindows().length === 0) (isFirstRun() ? runFirstTimeSetup : boot)();
    });
});

// IMPORTANT: On close, stop everything we started
function shutdownAll() {
    try {
        unloadOllamaModelsBestEffort();
    } catch (_) { }

    try {
        if (backendProc) {
            try { backendProc.kill("SIGTERM"); } catch (_) { }
            backendProc = null;
        }
    } catch (_) { }

    // Kill Vite + backend ports (mac)
    killPortsMac([5173, 7824, 7825]);
}

app.on("before-quit", () => shutdownAll());
app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
});
process.on("exit", () => shutdownAll());
process.on("SIGINT", () => { shutdownAll(); app.quit(); });
process.on("SIGTERM", () => { shutdownAll(); app.quit(); });