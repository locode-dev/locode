const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("locode", {
    onStatus: (cb) => ipcRenderer.on("status", (_e, msg) => cb(msg)),
    onLog: (cb) => ipcRenderer.on("log", (_e, line) => cb(line)),
});