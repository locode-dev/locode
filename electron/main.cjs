// electron/main.cjs
"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell, Menu, nativeImage } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");
const { spawn } = require("child_process");

const { ensureOllamaInstalled, findOllamaBinary, startOllama } = require("./ollama-bootstrap.cjs");

// ── Set dock icon as early as possible (before any window is created) ─────────
// In dev mode, Electron runs inside Electron.app so macOS shows the Electron
// icon by default. dock.setIcon() overrides this at RUNTIME — the Dock entry
// shows the correct icon once the app is running, but the Dock's static icon
// (before launch) still shows Electron. This is a macOS limitation in dev mode.
// In the packaged DMG, the correct icon is used everywhere.
if (process.platform === "darwin") {
    const _iconCandidates = [
        path.join(__dirname, "..", "assets", "locode.icns"),
        path.join(__dirname, "..", "assets", "locode.png"),
    ];
    for (const _p of _iconCandidates) {
        if (fs.existsSync(_p)) {
            try {
                const _img = nativeImage.createFromPath(_p);
                if (!_img.isEmpty()) {
                    // Set now for immediate effect
                    app.dock.setIcon(_img);
                    // Also set again once app is ready, in case first call was too early
                    app.once("ready", () => {
                        try { app.dock.setIcon(_img); } catch (_) { }
                    });
                    console.log("[icon] Dock icon set:", _p);
                    break;
                }
            } catch (_e) {
                console.warn("[icon] Failed to set dock icon:", _e.message);
            }
        }
    }
}

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
    const exeName = process.platform === "win32"
        ? "locode-backend-v4.exe"
        : "locode-backend-v4";
    if (app.isPackaged) return path.join(process.resourcesPath, "backend", exeName);
    return path.join(__dirname, "..", "server.py");  // dev mode: python server.py
}

function nodeBinDir() {
    if (isPackaged()) return path.join(getResourcesPath(), "node", process.platform === "win32" ? "" : "bin");
    return "";
}

function nodePath() {
    const bin = process.platform === "win32" ? "node.exe" : "node";
    const dir = process.platform === "win32" ? "" : "bin";
    if (app.isPackaged) return path.join(process.resourcesPath, "node", dir, bin).replace(/\/$/, "").replace(/\\$/, "");
    return process.env.LOCODE_NODE || process.env.NODE || "node";
}

function npmPath() {
    const bin = process.platform === "win32" ? "npm.cmd" : "npm";
    const dir = process.platform === "win32" ? "" : "bin";
    if (isPackaged()) return path.join(getResourcesPath(), "node", dir, bin).replace(/\/$/, "").replace(/\\$/, "");
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

function getIconPath() {
    // __dirname = locode/electron/ -> ".." = locode/
    const candidates = [];
    if (app.isPackaged) {
        candidates.push(path.join(process.resourcesPath, "locode.icns"));
        candidates.push(path.join(process.resourcesPath, "assets", "locode.icns"));
    }
    // Dev mode: .icns first, then .png fallback
    candidates.push(path.join(__dirname, "..", "assets", "locode.icns"));
    candidates.push(path.join(__dirname, "..", "assets", "locode.png"));
    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }
    return null;
}

function killPortsMac(ports = [5173, 7824, 7825]) {
    if (process.platform !== "darwin") return;
    try {
        spawn("bash", ["-lc", `lsof -ti :${ports.join(",")} | xargs kill -9 2>/dev/null || true`], { stdio: "ignore" });
    } catch (_) { }
}

function killPortsWin(ports = [5173, 7824, 7825]) {
    if (process.platform !== "win32") return;
    const { execSync } = require("child_process");
    for (const port of ports) {
        try {
            const out = execSync(`netstat -ano | findstr :${port}`, { encoding: "utf8" }).trim();
            for (const line of out.split("\n").filter(l => l.includes("LISTENING"))) {
                const pid = line.trim().split(/\s+/).pop();
                if (pid && parseInt(pid) > 4) {
                    try { execSync(`taskkill /PID ${pid} /F`, { stdio: "ignore" }); } catch (_) { }
                }
            }
        } catch (_) { }
    }
}

// Optional: unload all models quickly on quit (does NOT stop Ollama daemon, just unloads VRAM)
function unloadOllamaModelsBestEffort() {
    try {
        const curl = spawn("bash", ["-lc", `curl -s http://127.0.0.1:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":0}' >/dev/null 2>&1 || true; curl -s http://127.0.0.1:11434/api/generate -d '{"model":"qwen2.5-coder:14b","keep_alive":0}' >/dev/null 2>&1 || true`], { stdio: "ignore" });
        curl.on("error", () => { });
    } catch (_) { }
}

function createSplash() {
    const icon = getIconPath();
    splashWin = new BrowserWindow({
        width: 560,
        height: 500,
        resizable: false,
        frame: false,
        backgroundColor: "#0b0f19",
        ...(icon ? { icon } : {}),
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
    const icon = getIconPath();
    setupWin = new BrowserWindow({
        width: 560,
        height: 500,
        resizable: false,
        frame: false,
        backgroundColor: "#080b12",
        ...(icon ? { icon } : {}),
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
    const icon = getIconPath();
    mainWin = new BrowserWindow({
        title: "Locode — Local AI App Builder",
        width: 1280,
        height: 820,
        show: false,
        ...(icon ? { icon } : {}),
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

function startBackend(extraEnv = {}) {
    const browsersPath = playwrightBrowsersPath();
    const nodeDir = path.dirname(nodePath());
    const pathSep = process.platform === "win32" ? ";" : ":";
    const curPath = process.env.PATH || "";
    const newPath = nodeDir && !curPath.includes(nodeDir)
        ? `${nodeDir}${pathSep}${curPath}`
        : curPath;

    const env = {
        ...process.env,
        PATH: newPath,
        LOCODE_NODE: nodePath(),
        LOCODE_NPM: npmPath(),
        PLAYWRIGHT_BROWSERS_PATH: browsersPath,
        PLAYWRIGHT_NODEJS_PATH: nodePath(),
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
        ...extraEnv,
    };

    sendStatus("Starting backend…");

    if (app.isPackaged) {
        const backendExe = backendPath();
        sendLog(`[backend] spawn packaged: ${backendExe}`);
        backendProc = spawn(backendExe, [], { env, stdio: "pipe" });
    } else {
        // Dev mode: run server.py directly with python3/python
        const pyBin = process.platform === "win32" ? "python" : "python3";
        const serverScript = path.join(__dirname, "..", "server.py");
        sendLog(`[backend] spawn dev: ${pyBin} ${serverScript}`);
        backendProc = spawn(pyBin, [serverScript], { env, stdio: "pipe" });
    }

    backendProc.stdout.on("data", d => {
        const s = d.toString().trimEnd();
        console.log("[backend]", s);
        sendLog(s);
    });
    backendProc.stderr.on("data", d => {
        const s = d.toString().trimEnd();
        console.error("[backend]", s);
        sendLog("ERR: " + s);
    });
    backendProc.on("exit", code => {
        sendLog(`[backend] exited with code ${code}`);
        backendProc = null;
    });
    backendProc.on("error", e => {
        sendLog(`[backend] spawn error: ${e.message}`);
    });
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

    // Dock icon is set at module load time (top of file) for earliest possible effect

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

    // Kill Vite + backend ports
    killPortsMac([5173, 7824, 7825]);
    killPortsWin([5173, 7824, 7825]);
}

app.on("before-quit", () => shutdownAll());
app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
});
process.on("exit", () => shutdownAll());
process.on("SIGINT", () => { shutdownAll(); app.quit(); });
process.on("SIGTERM", () => { shutdownAll(); app.quit(); });