const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("locode", {
    // Splash / boot status
    onStatus: (cb) => ipcRenderer.on("status", (_e, msg) => cb(msg)),
    onLog: (cb) => ipcRenderer.on("log", (_e, line) => cb(line)),

    // Setup screen progress (first-run only)
    onSetup: (cb) => ipcRenderer.on("setup", (_e, msg) => cb(msg)),

    // Folder picker — returns { name, files, fileCount } or null
    chooseFolder: () => ipcRenderer.invoke("choose-folder"),

    // Open URL in system browser
    openExternal: (url) => ipcRenderer.invoke("open-external", url),
});
