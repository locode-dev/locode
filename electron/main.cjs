const { app, BrowserWindow, dialog, nativeImage, ipcMain, shell, Menu } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const net = require("net");
const fs = require("fs");

const { ensureOllamaInstalled, findOllamaBinary, startOllama } = require("./ollama-bootstrap.cjs");

let backendProc = null;
let splashWin = null;
let setupWin = null;
let mainWin = null;

backendProcess = spawn("python", ["server.py"])

app.on("before-quit", () => {
    if (backendProcess) {
        backendProcess.kill("SIGTERM")
    }
})

process.on("exit", () => {
    if (backendProcess) {
        backendProcess.kill("SIGTERM")
    }
})

// ── First-run detection ──────────────────────────────────────────────────────
const FIRST_RUN_FLAG = path.join(app.getPath("userData"), ".locode-initialized");
function isFirstRun() { return !fs.existsSync(FIRST_RUN_FLAG); }
function markInitialized() {
    try { fs.writeFileSync(FIRST_RUN_FLAG, new Date().toISOString()); } catch (_) { }
}

// ── Packaged helpers ─────────────────────────────────────────────────────────
function isPackaged() { return app.isPackaged; }
function getResourcesPath() { return process.resourcesPath; }
function backendPath() {
    if (isPackaged()) return path.join(process.resourcesPath, "backend", "locode-backend-v4");
    return path.join(__dirname, "..", "server.py");
}
function nodePath() {
    if (isPackaged()) return path.join(process.resourcesPath, "node", "bin", "node");
    return process.env.LOCODE_NODE || process.env.NODE || "node";
}
function npmPath() {
    if (isPackaged()) return path.join(process.resourcesPath, "node", "bin", "npm");
    return process.env.LOCODE_NPM || process.env.NPM || "npm";
}

// ── Messaging helpers ────────────────────────────────────────────────────────
function sendSetup(msg) {
    try { if (setupWin && !setupWin.isDestroyed()) setupWin.webContents.send("setup", msg); } catch (_) { }
}
function sendStatus(msg) {
    try { if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("status", msg); } catch (_) { }
}
function sendLog(line) {
    try {
        if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("log", line);
        if (setupWin && !setupWin.isDestroyed()) setupWin.webContents.send("log", line);
    } catch (_) { }
}

function waitForPort(port, host = "127.0.0.1", timeoutMs = 40000) {
    const start = Date.now();
    return new Promise((resolve, reject) => {
        const tick = () => {
            const socket = net.createConnection(port, host);
            socket.once("connect", () => { socket.end(); resolve(true); });
            socket.once("error", () => {
                socket.destroy();
                if (Date.now() - start > timeoutMs) reject(new Error(`Timed out waiting for ${host}:${port}`));
                else setTimeout(tick, 250);
            });
        };
        tick();
    });
}

// ── Setup window (first run only) ────────────────────────────────────────────
function createSetupWindow() {
    setupWin = new BrowserWindow({
        width: 560, height: 500,
        resizable: false, frame: false,
        backgroundColor: "#080b12",
        webPreferences: {
            contextIsolation: true,
            preload: require('fs').existsSync(path.join(__dirname, 'preload.cjs')) ? path.join(__dirname, 'preload.cjs') : path.join(__dirname, 'preload.js'),
        }
    });
    setupWin.loadFile(path.join(__dirname, "setup.html"));
}

// ── Splash window (returning users) ─────────────────────────────────────────
function createSplash() {
    splashWin = new BrowserWindow({
        width: 560, height: 500,
        resizable: false, frame: false,
        backgroundColor: "#0b0f19",
        icon: path.join(__dirname, "..", "build", "locode.icns"),
        webPreferences: {
            contextIsolation: true,
            preload: require('fs').existsSync(path.join(__dirname, 'preload.cjs')) ? path.join(__dirname, 'preload.cjs') : path.join(__dirname, 'preload.js'),
        }
    });
    splashWin.loadFile(path.join(__dirname, "splash.html"));
}

// ── Main window ──────────────────────────────────────────────────────────────
function createMainWindow() {
    mainWin = new BrowserWindow({
        title: "Locode — Local AI App Builder",
        width: 1280, height: 820, show: false,
        icon: path.join(__dirname, "..", "build", "locode.icns"),
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            preload: require('fs').existsSync(path.join(__dirname, 'preload.cjs')) ? path.join(__dirname, 'preload.cjs') : path.join(__dirname, 'preload.js'),
        }
    });
    mainWin.on("ready-to-show", () => {
        mainWin.show();
        if (splashWin && !splashWin.isDestroyed()) splashWin.close();
        if (setupWin && !setupWin.isDestroyed()) setupWin.close();
    });
    return mainWin;
}

function playwrightBrowsersPath() {
    if (isPackaged()) return path.join(process.resourcesPath, "ms-playwright");
    return path.join(__dirname, "..", "vendor", "ms-playwright");
}

function startBackend(extraEnv = {}) {
    const backendScript = backendPath();
    const nodeBin = isPackaged() ? path.join(getResourcesPath(), "node", "bin") : "";
    const browsersPath = playwrightBrowsersPath();
    const env = {
        ...process.env,
        LOCODE_NODE: nodePath(),
        LOCODE_NPM: npmPath(),
        ...(nodeBin ? { PATH: `${nodeBin}:${process.env.PATH || ""}` } : {}),
        PLAYWRIGHT_BROWSERS_PATH: browsersPath,
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: "1",
        ...extraEnv
    };

    sendStatus("Starting backend…");

    if (isPackaged()) {
        sendLog(`[backend] spawn: ${backendScript}`);
        backendProc = spawn(backendScript, [], { env, stdio: "pipe" });
    } else {
        sendLog(`[backend] spawn: python3 ${backendScript}`);
        backendProc = spawn("python3", [backendScript], { env, stdio: "pipe" });
    }

    backendProc.stdout.on("data", d => { const s = d.toString().trimEnd(); console.log("[backend]", s); sendLog(s); });
    backendProc.stderr.on("data", d => { const s = d.toString().trimEnd(); console.error("[backend]", s); sendLog("ERR: " + s); });
    backendProc.on("exit", code => { sendLog(`[backend] exited: ${code}`); backendProc = null; });
    backendProc.on("error", e => { sendLog(`[backend] spawn error: ${e.message}`); });
}

// ── IPC: folder picker for project upload ─────────────────────────────────────
ipcMain.handle("choose-folder", async () => {
    const win = mainWin || BrowserWindow.getFocusedWindow();
    const result = await dialog.showOpenDialog(win, {
        properties: ["openDirectory"],
        title: "Select your React project folder",
        buttonLabel: "Import Project"
    });
    if (result.canceled || !result.filePaths.length) return null;

    const folderPath = result.filePaths[0];
    const folderName = path.basename(folderPath);
    const files = {};
    const allowedExts = new Set([".jsx", ".tsx", ".js", ".ts", ".css", ".html", ".json", ".md", ".svg"]);
    const skipDirs = new Set(["node_modules", ".git", "dist", "build", ".next", "out", ".cache", ".turbo"]);

    function walkDir(dir, base) {
        let entries;
        try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch (_) { return; }
        for (const entry of entries) {
            if (skipDirs.has(entry.name)) continue;
            const fullPath = path.join(dir, entry.name);
            const relPath = base ? `${base}/${entry.name}` : entry.name;
            if (entry.isDirectory()) {
                walkDir(fullPath, relPath);
            } else {
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

// ── IPC: open external URL ────────────────────────────────────────────────────
ipcMain.handle("open-external", async (_, url) => { await shell.openExternal(url); });

// ── First-time setup flow ─────────────────────────────────────────────────────
async function runFirstTimeSetup() {
    createSetupWindow();
    createMainWindow();
    await new Promise(r => setTimeout(r, 900));

    // 1) Check Ollama
    sendSetup({ type: "step", step: "ollama", status: "active", label: "Checking Ollama…" });
    sendSetup({ type: "progress", pct: 8, label: "Checking Ollama installation…" });

    const res = await ensureOllamaInstalled();
    if (res.status === "needs-install") {
        sendSetup({ type: "step", step: "ollama", status: "error", label: "Ollama not found" });
        const choice = await dialog.showMessageBox(setupWin, {
            type: "info",
            buttons: ["Open Download Page", "Cancel"],
            title: "Install Ollama",
            message: "Ollama is required to run Locode.",
            detail: "1) Download and install Ollama from ollama.com\n2) Launch Ollama\n3) Re-open Locode"
        });
        if (choice.response === 0) shell.openExternal("https://ollama.com/download");
        app.quit(); return;
    }
    sendSetup({ type: "step", step: "ollama", status: "done", label: "Ollama found ✓" });
    sendSetup({ type: "progress", pct: 28, label: "Ollama ready" });

    // 2) Start Ollama server
    sendSetup({ type: "step", step: "ollama-server", status: "active", label: "Starting Ollama server…" });
    sendSetup({ type: "progress", pct: 38, label: "Starting Ollama server…" });

    const ollamaBin = findOllamaBinary();
    if (ollamaBin) { await startOllama(ollamaBin); sendLog("[ollama] started"); }

    sendSetup({ type: "step", step: "ollama-server", status: "done", label: "Ollama server running ✓" });
    sendSetup({ type: "progress", pct: 55, label: "Ollama server running" });

    // 3) Start backend
    sendSetup({ type: "step", step: "backend", status: "active", label: "Starting Locode backend…" });
    sendSetup({ type: "progress", pct: 62, label: "Starting backend…" });
    startBackend();

    // 4) Wait for UI port
    sendSetup({ type: "step", step: "ui", status: "active", label: "Connecting to services…" });
    sendSetup({ type: "progress", pct: 72, label: "Waiting for services…" });

    await waitForPort(7824, "127.0.0.1", 60000);

    sendSetup({ type: "step", step: "backend", status: "done", label: "Backend ready ✓" });
    sendSetup({ type: "step", step: "ui", status: "done", label: "All services ready ✓" });
    sendSetup({ type: "progress", pct: 96, label: "Launching…" });

    markInitialized();
    await new Promise(r => setTimeout(r, 500));
    sendSetup({ type: "launch" });
    await mainWin.loadURL(`http://127.0.0.1:7824/?cb=${Date.now()}`);
}

// ── Normal boot ───────────────────────────────────────────────────────────────
async function boot() {
    createSplash();
    createMainWindow();

    sendStatus("Checking Ollama…");
    const res = await ensureOllamaInstalled();
    if (res.status === "needs-install") {
        sendStatus("Ollama not installed. Opening installer…");
        await dialog.showMessageBox({
            type: "info", buttons: ["OK"], title: "Install Ollama",
            message: "Ollama is required to run Locode.",
            detail: "An Ollama installer DMG has been opened.\n\n1) Drag Ollama to Applications\n2) Launch Ollama once\n3) Re-open Locode"
        });
        app.quit(); return;
    }

    sendStatus("Starting services…");
    const ollamaBin = findOllamaBinary();
    if (ollamaBin) { await startOllama(ollamaBin); sendLog("[ollama] started"); }

    startBackend();

    sendStatus("Connecting to Locode UI…");
    await waitForPort(7824, "127.0.0.1", 60000);

    sendStatus("Loading app…");
    await mainWin.loadURL(`http://127.0.0.1:7824/?cb=${Date.now()}`);
}

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
                { role: "quit" }
            ]
        },
        { role: "editMenu" },
        { role: "viewMenu" },
        { role: "windowMenu" },
        {
            label: "Maintenance",
            submenu: [
                {
                    label: "Factory Reset (Clear all data)",
                    click: async () => {
                        const { response } = await dialog.showMessageBox({
                            type: "warning",
                            buttons: ["Cancel", "Yes, Reset Everything"],
                            title: "Factory Reset",
                            message: "Are you sure you want to reset Locode?",
                            detail: "This will delete all your settings, projects, and the initialization flag. The app will quit after reset.",
                            noLink: true
                        });
                        if (response === 1) {
                            const userData = app.getPath("userData");
                            console.log("Resetting app data in:", userData);
                            try {
                                // Kill backend for safety
                                if (backendProc) backendProc.kill("SIGKILL");

                                // Recursively delete userData
                                fs.rmSync(userData, { recursive: true, force: true });

                                await dialog.showMessageBox({
                                    type: "info",
                                    title: "Reset Successful",
                                    message: "Locode has been reset. Please relaunch the app."
                                });
                                app.quit();
                            } catch (e) {
                                dialog.showErrorBox("Reset Failed", e.message);
                            }
                        }
                    }
                },
                {
                    label: "Open App Data Folder",
                    click: () => { shell.openPath(app.getPath("userData")); }
                }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
}

// ── App init ─────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
    setupMenu();
    // Clear disk cache so index.html is always fresh
    const { session } = require("electron");
    session.defaultSession.clearCache().catch(() => { });
    if (process.platform === "darwin") {
        const iconPath = path.join(__dirname, "..", "assets", "locode.png");
        const image = nativeImage.createFromPath(iconPath);
        if (!image.isEmpty()) { app.dock.setIcon(image); console.log("Dock icon set"); }
        else { console.error("Failed to load icon from:", iconPath); }
    }

    const startFn = isFirstRun() ? runFirstTimeSetup : boot;
    startFn().catch(async (e) => {
        console.error(e);
        try {
            sendStatus("Startup failed.");
            sendSetup({ type: "error", message: e?.message || String(e) });
            sendLog("FATAL: " + (e?.stack || e?.message || String(e)));
        } catch (_) { }
        await dialog.showMessageBox({
            type: "error", title: "Locode failed to start",
            message: "Startup failed",
            detail: e?.stack || e?.message || String(e)
        });
        app.quit();
    });

    app.on("activate", async () => {
        if (BrowserWindow.getAllWindows().length === 0)
            (isFirstRun() ? runFirstTimeSetup : boot)();
    });
});

app.on("before-quit", () => { if (backendProc) { try { backendProc.kill("SIGTERM"); } catch (_) { } } });
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
