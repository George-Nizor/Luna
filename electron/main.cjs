"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

const APP_ID = "com.instrumenta.luna";
const START_PORT = 7865;
const START_TIMEOUT_MS = 90_000;
const STOP_TIMEOUT_MS = 15_000;

let mainWindow = null;
let backendProcess = null;
let backendPort = null;
let backendToken = null;
let backendStopping = false;
let quitting = false;
let shutdownComplete = false;

app.setAppUserModelId(APP_ID);

function projectRoot() {
  return path.resolve(__dirname, "..");
}

function runtimePaths() {
  const userRoot = app.getPath("userData");
  const packaged = app.isPackaged;
  return {
    backendRoot: packaged ? path.join(process.resourcesPath, "backend") : projectRoot(),
    python: packaged
      ? path.join(process.resourcesPath, "python", "python.exe")
      : path.join(projectRoot(), ".venv", "Scripts", "python.exe"),
    data: path.join(userRoot, "data"),
    runtime: path.join(userRoot, "runtime"),
    logs: path.join(userRoot, "logs"),
    models: packaged ? path.join(process.resourcesPath, "model-data", "models") : path.join(projectRoot(), "data", "models"),
    hfHome: packaged ? path.join(userRoot, "model_cache") : path.join(projectRoot(), "data", "model_cache"),
    qwenFast: packaged ? path.join(process.resourcesPath, "model-data", "qwen", "qwen-fast") : null,
    qwenBest: packaged ? path.join(process.resourcesPath, "model-data", "qwen", "qwen-best") : null,
  };
}

function settingsPath() {
  return path.join(app.getPath("userData"), "desktop-settings.json");
}

function defaultOutputDirectory() {
  return path.join(app.getPath("documents"), "Luna");
}

function readDesktopSettings() {
  try {
    const parsed = JSON.parse(fs.readFileSync(settingsPath(), "utf8"));
    if (typeof parsed.outputDirectory === "string" && path.isAbsolute(parsed.outputDirectory)) return parsed;
  } catch (_) {
    // First launch or a damaged settings file falls back to a safe default.
  }
  return { outputDirectory: defaultOutputDirectory() };
}

function writeDesktopSettings(settings) {
  fs.mkdirSync(path.dirname(settingsPath()), { recursive: true });
  const temporary = `${settingsPath()}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(settings, null, 2), "utf8");
  fs.renameSync(temporary, settingsPath());
}

function outputDirectory() {
  const directory = readDesktopSettings().outputDirectory;
  fs.mkdirSync(directory, { recursive: true });
  return directory;
}

function findAvailablePort(start = START_PORT) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      const server = net.createServer();
      server.unref();
      server.once("error", (error) => {
        server.close();
        if (error.code === "EADDRINUSE" && port < start + 50) tryPort(port + 1);
        else reject(error);
      });
      server.listen({ host: "127.0.0.1", port, exclusive: true }, () => {
        const selected = server.address().port;
        server.close(() => resolve(selected));
      });
    };
    tryPort(start);
  });
}

function healthCheck(port) {
  return new Promise((resolve) => {
    const request = http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 1200 }, (response) => {
      response.resume();
      resolve(response.statusCode === 200);
    });
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve(false));
  });
}

function readBackendToken(paths) {
  try {
    const runtime = JSON.parse(fs.readFileSync(path.join(paths.runtime, "app.json"), "utf8"));
    return typeof runtime.token === "string" ? runtime.token : null;
  } catch (_) {
    return null;
  }
}

async function waitForBackend(port, paths) {
  const started = Date.now();
  while (Date.now() - started < START_TIMEOUT_MS) {
    if (backendProcess && backendProcess.exitCode !== null) {
      throw new Error(`Voice engine exited during startup (code ${backendProcess.exitCode}).`);
    }
    if (await healthCheck(port)) {
      backendToken = readBackendToken(paths);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("The local voice engine did not become ready within 90 seconds.");
}

async function startBackend() {
  const paths = runtimePaths();
  for (const directory of [paths.data, paths.runtime, paths.logs, paths.hfHome, outputDirectory()]) {
    fs.mkdirSync(directory, { recursive: true });
  }
  const requiredPaths = [paths.python, path.join(paths.backendRoot, "run.py"), paths.models];
  if (app.isPackaged) requiredPaths.push(paths.qwenFast, paths.qwenBest);
  for (const required of requiredPaths) {
    if (!fs.existsSync(required)) throw new Error(`The installed runtime is incomplete: ${required}`);
  }

  backendPort = await findAvailablePort();
  const logPath = path.join(paths.logs, "desktop-backend.log");
  const log = fs.openSync(logPath, "a");
  const env = {
    ...process.env,
    HOST: "127.0.0.1",
    PORT: String(backendPort),
    APP_IDLE_SHUTDOWN_SECONDS: "0",
    DATA_DIRECTORY: paths.data,
    OUTPUT_DIRECTORY: outputDirectory(),
    MODELS_DIRECTORY: paths.models,
    HF_HOME: paths.hfHome,
    RUNTIME_DIRECTORY: paths.runtime,
    LOG_DIRECTORY: paths.logs,
    OFFLINE_MODE: app.isPackaged ? "true" : (process.env.OFFLINE_MODE || "false"),
    PYTHONNOUSERSITE: "1",
    PYTHONUNBUFFERED: "1",
  };
  if (paths.qwenFast && paths.qwenBest) {
    env.QWEN_FAST_PATH = paths.qwenFast;
    env.QWEN_BEST_PATH = paths.qwenBest;
  }
  backendProcess = spawn(paths.python, ["run.py"], {
    cwd: paths.backendRoot,
    env,
    windowsHide: true,
    stdio: ["ignore", log, log],
  });
  fs.closeSync(log);
  backendProcess.once("exit", (code) => {
    backendProcess = null;
    backendToken = null;
    if (!quitting && !backendStopping && mainWindow && !mainWindow.isDestroyed()) {
      dialog.showErrorBox("Voice engine stopped", `The local voice engine exited unexpectedly (code ${code}).\n\nSee ${logPath}`);
    }
  });
  await waitForBackend(backendPort, paths);
}

function requestBackendShutdown() {
  if (!backendPort || !backendToken) return Promise.resolve();
  return new Promise((resolve) => {
    const request = http.request({
      host: "127.0.0.1",
      port: backendPort,
      path: "/api/app/shutdown",
      method: "POST",
      timeout: 2000,
      headers: {
        "X-Local-Token": backendToken,
        "Content-Type": "application/json",
        "Content-Length": "2",
      },
    }, (response) => {
      response.resume();
      response.on("end", resolve);
    });
    request.on("timeout", () => { request.destroy(); resolve(); });
    request.on("error", resolve);
    request.end("{}");
  });
}

async function stopBackend() {
  const processToStop = backendProcess;
  if (!processToStop) return;
  backendStopping = true;
  try {
    await requestBackendShutdown();
    const exited = processToStop.exitCode !== null ? true : await new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), STOP_TIMEOUT_MS);
      processToStop.once("exit", () => { clearTimeout(timer); resolve(true); });
    });
    if (!exited && processToStop.exitCode === null) {
      processToStop.kill();
      await new Promise((resolve) => setTimeout(resolve, 2500));
    }
    backendProcess = null;
    backendToken = null;
    backendPort = null;
  } finally {
    backendStopping = false;
  }
}

function createWindow() {
  const windowIcon = app.isPackaged
    ? path.join(process.resourcesPath, "assets", "luna-icon.png")
    : path.join(projectRoot(), "assets", "luna-icon.png");
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 960,
    minHeight: 700,
    show: false,
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    title: "Luna",
    icon: windowIcon,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: true,
    },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https:\/\//i.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = `http://127.0.0.1:${backendPort}/`;
    if (!url.startsWith(allowed)) event.preventDefault();
  });
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => { mainWindow = null; });
  mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
}

async function restartBackend() {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.hide();
  await stopBackend();
  await startBackend();
  if (mainWindow && !mainWindow.isDestroyed()) {
    await mainWindow.loadURL(`http://127.0.0.1:${backendPort}/`);
    mainWindow.show();
  }
}

function registerIpc() {
  ipcMain.handle("studio:get-output-directory", () => outputDirectory());
  ipcMain.handle("studio:open-output-directory", () => shell.openPath(outputDirectory()));
  ipcMain.handle("studio:choose-output-directory", async () => {
    const selection = await dialog.showOpenDialog(mainWindow, {
      title: "Choose where generated sounds are stored",
      defaultPath: outputDirectory(),
      properties: ["openDirectory", "createDirectory"],
    });
    if (selection.canceled || selection.filePaths.length !== 1) return { changed: false, path: outputDirectory() };
    const selected = path.resolve(selection.filePaths[0]);
    fs.mkdirSync(selected, { recursive: true });
    fs.accessSync(selected, fs.constants.R_OK | fs.constants.W_OK);
    if (selected === outputDirectory()) return { changed: false, path: selected };
    writeDesktopSettings({ outputDirectory: selected });
    await restartBackend();
    return { changed: true, path: selected };
  });
  ipcMain.handle("studio:get-runtime-info", () => ({ packaged: app.isPackaged, version: app.getVersion() }));
  ipcMain.handle("studio:shutdown", () => {
    setImmediate(() => app.quit());
    return true;
  });
}

const singleInstance = app.requestSingleInstanceLock();
if (!singleInstance) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      registerIpc();
      await startBackend();
      createWindow();
    } catch (error) {
      dialog.showErrorBox("Luna could not start", error.stack || error.message || String(error));
      quitting = true;
      await stopBackend();
      shutdownComplete = true;
      app.quit();
    }
  });
}

app.on("window-all-closed", () => app.quit());
app.on("before-quit", (event) => {
  if (shutdownComplete) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  stopBackend().finally(() => {
    shutdownComplete = true;
    app.quit();
  });
});
