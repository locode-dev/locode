const { app, BrowserWindow, dialog, nativeImage } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const net = require("net");

const { ensureOllamaInstalled, findOllamaBinary, startOllama } = require("./ollama-bootstrap.cjs");

let backendProc = null;
let splashWin = null;
let mainWin = null;

function isPackaged() {
    return app.isPackaged;
}

function getResourcesPath() {
    return process.resourcesPath;
}

function backendPath() {
    if (isPackaged()) return path.join(process.resourcesPath, "backend", "locode-backend");
    return path.join(__dirname, "..", "dist-backend", "locode-backend");
}

function nodePath() {
    if (isPackaged()) return path.join(process.resourcesPath, "node", "bin", "node");
    return process.env.LOCODE_NODE || process.env.NODE || "node";
}

function npmPath() {
    if (isPackaged()) return path.join(process.resourcesPath, "node", "bin", "npm");
    return process.env.LOCODE_NPM || process.env.NPM || "npm";
}

function sendStatus(msg) {
    try {
        if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("status", msg);
    } catch { }
}

function sendLog(line) {
    try {
        if (splashWin && !splashWin.isDestroyed()) splashWin.webContents.send("log", line);
    } catch { }
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

function createSplash() {
    splashWin = new BrowserWindow({
        width: 520,
        height: 420,
        resizable: false,
        frame: false, // Optional: Splash screens usually look better without a frame
        backgroundColor: "#0b0f19",
        icon: path.join(__dirname, "..", "build", "locode.icns"), // Adjusted path
        webPreferences: {
            contextIsolation: true,
            preload: path.join(__dirname, "preload.cjs"),
        }
    });

    splashWin.loadFile(path.join(__dirname, "splash.html"));
}

function createMainWindow() {
    mainWin = new BrowserWindow({
        width: 1280,
        height: 820,
        show: false,
        icon: path.join(__dirname, "..", "build", "locode.icns"), // Adjusted path
        webPreferences: {
            contextIsolation: true
        }
    });

    mainWin.on("ready-to-show", () => {
        mainWin.show();
        if (splashWin && !splashWin.isDestroyed()) splashWin.close();
    });

    return mainWin;
}

function startBackend(extraEnv = {}) {
    const exe = backendPath();

    const nodeBin = isPackaged() ? path.join(getResourcesPath(), "node", "bin") : "";
    const browsersPath = isPackaged() ? path.join(getResourcesPath(), "ms-playwright") : "";

    const env = {
        ...process.env,
        LOCODE_NODE: nodePath(),
        LOCODE_NPM: npmPath(),
        ...(nodeBin ? { PATH: `${nodeBin}:${process.env.PATH || ""}` } : {}),

        ...(browsersPath ? { PLAYWRIGHT_BROWSERS_PATH: browsersPath } : {}),
        PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: isPackaged() ? "1" : (process.env.PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD || ""),

        ...extraEnv
    };

    sendStatus("Starting backend…");
    sendLog(`[backend] spawn: ${exe}`);

    backendProc = spawn(exe, [], { env, stdio: "pipe" });

    backendProc.stdout.on("data", (d) => {
        const s = d.toString().trimEnd();
        console.log("[backend]", s);
        sendLog(s);
    });

    backendProc.stderr.on("data", (d) => {
        const s = d.toString().trimEnd();
        console.error("[backend]", s);
        sendLog("ERR: " + s);
    });

    backendProc.on("exit", (code) => {
        sendLog(`[backend] exited with code: ${code}`);
        backendProc = null;
    });

    backendProc.on("error", (e) => {
        sendLog(`[backend] spawn error: ${e.message}`);
    });
}

async function boot() {
    createSplash();
    createMainWindow();

    sendStatus("Checking Ollama…");

    // 1) Ollama check / install guidance
    const res = await ensureOllamaInstalled();
    if (res.status === "needs-install") {
        sendStatus("Ollama not installed. Opening installer…");
        await dialog.showMessageBox({
            type: "info",
            buttons: ["OK"],
            title: "Install Ollama",
            message: "Ollama is required to run Locode.",
            detail:
                "An Ollama installer DMG has been opened.\n\n" +
                "1) Drag Ollama to Applications\n" +
                "2) Launch Ollama once (it will start the local server)\n" +
                "3) Re-open Locode"
        });
        app.quit();
        return;
    }

    // 2) Start Ollama best-effort
    sendStatus("Starting Ollama…");
    const ollamaBin = findOllamaBinary();
    if (ollamaBin) {
        await startOllama(ollamaBin);
        sendLog("[ollama] started (best-effort)");
    } else {
        sendLog("[ollama] binary not found after install step (unexpected)");
    }

    // 3) Start backend
    startBackend();

    // 4) Wait for backend UI
    sendStatus("Waiting for Locode UI (http://localhost:7824)…");
    await waitForPort(7824, "127.0.0.1", 60000);

    sendStatus("Loading app…");
    await mainWin.loadURL("http://localhost:7824");
}

app.whenReady().then(() => {
    if (process.platform === 'darwin') {
        // Pointing directly to your assets folder
        const iconPath = path.join(__dirname, "..", "assets", "locode.png");

        const image = nativeImage.createFromPath(iconPath);

        if (!image.isEmpty()) {
            app.dock.setIcon(image);
            console.log("Success: Dock icon updated using locode.png");
        } else {
            console.error("Failed to load icon from:", iconPath);
        }
    }
    boot().catch(async (e) => {
        console.error(e);
        try {
            sendStatus("Startup failed.");
            sendLog("FATAL: " + (e?.stack || e?.message || String(e)));
        } catch { }

        await dialog.showMessageBox({
            type: "error",
            title: "Locode failed to start",
            message: "Startup failed",
            detail: e?.stack || e?.message || String(e)
        });

        app.quit();
    });

    app.on("activate", async () => {
        if (BrowserWindow.getAllWindows().length === 0) boot();
    });
});

app.on("before-quit", () => {
    if (backendProc) {
        try { backendProc.kill("SIGTERM"); } catch { }
    }
});

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
});