"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("voiceStudio", Object.freeze({
  getOutputDirectory: () => ipcRenderer.invoke("studio:get-output-directory"),
  chooseOutputDirectory: () => ipcRenderer.invoke("studio:choose-output-directory"),
  openOutputDirectory: () => ipcRenderer.invoke("studio:open-output-directory"),
  getRuntimeInfo: () => ipcRenderer.invoke("studio:get-runtime-info"),
  shutdown: () => ipcRenderer.invoke("studio:shutdown"),
}));
