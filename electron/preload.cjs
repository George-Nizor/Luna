"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("voiceStudio", Object.freeze({
  getOutputDirectory: () => ipcRenderer.invoke("studio:get-output-directory"),
  chooseOutputDirectory: () => ipcRenderer.invoke("studio:choose-output-directory"),
  openOutputDirectory: () => ipcRenderer.invoke("studio:open-output-directory"),
  revealOutput: (id) => ipcRenderer.invoke("studio:reveal-output", id),
  exportOutput: (id) => ipcRenderer.invoke("studio:export-output", id),
  getRuntimeInfo: () => ipcRenderer.invoke("studio:get-runtime-info"),
  shutdown: () => ipcRenderer.invoke("studio:shutdown"),
}));

// The first-run runtime setup screen (electron/setup). The main process answers these only while
// that screen is showing.
contextBridge.exposeInMainWorld("lunaSetup", Object.freeze({
  getState: () => ipcRenderer.invoke("setup:state"),
  start: () => ipcRenderer.invoke("setup:start"),
  cancel: () => ipcRenderer.invoke("setup:cancel"),
  proceed: () => ipcRenderer.invoke("setup:proceed"),
  quit: () => ipcRenderer.invoke("setup:quit"),
  onProgress: (callback) => {
    ipcRenderer.removeAllListeners("setup:progress");
    ipcRenderer.on("setup:progress", (_event, update) => callback(update));
  },
}));
