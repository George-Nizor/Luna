const path = require("node:path");

const projectRoot = __dirname;
const installedPayloadRoot = process.env.LUNA_INSTALLED_PAYLOAD_ROOT
  ? path.resolve(process.env.LUNA_INSTALLED_PAYLOAD_ROOT)
  : "";
const pythonBase = installedPayloadRoot
  ? path.join(installedPayloadRoot, "python")
  : process.env.VOICE_STUDIO_PYTHON_BASE;
if (!pythonBase) {
  throw new Error("VOICE_STUDIO_PYTHON_BASE or LUNA_INSTALLED_PAYLOAD_ROOT must supply the local Python runtime.");
}

const modelSource = installedPayloadRoot
  ? path.join(installedPayloadRoot, "model-data", "models")
  : path.join(projectRoot, "data", "models");
const qwenSource = installedPayloadRoot
  ? path.join(installedPayloadRoot, "model-data", "qwen")
  : path.join(projectRoot, "build", "model-payload");

const extraResources = [
  {
    from: path.join(projectRoot, "app"),
    to: "backend/app",
    filter: ["**/*", "!**/__pycache__/**", "!**/*.pyc"],
  },
  { from: path.join(projectRoot, "run.py"), to: "backend/run.py" },
  {
    from: pythonBase,
    to: "python",
    filter: ["**/*", "!**/__pycache__/**", "!**/*.pyc", "!include/**", "!libs/**", "!Scripts/**"],
  },
  ...(!installedPayloadRoot ? [{
    from: path.join(projectRoot, ".venv", "Lib", "site-packages"),
    to: "python/Lib/site-packages",
    filter: ["**/*", "!**/__pycache__/**", "!**/*.pyc", "!**/*.pyo", "!**/tests/**", "!**/test/**"],
  }] : []),
  { from: modelSource, to: "model-data/models", filter: ["**/*", "!.gitkeep"] },
  { from: qwenSource, to: "model-data/qwen", filter: ["**/*"] },
  { from: path.join(projectRoot, "assets", "luna-icon.png"), to: "assets/luna-icon.png" },
];

module.exports = {
  appId: "com.instrumenta.luna",
  productName: "Luna",
  copyright: "Copyright © 2026",
  asar: true,
  // ML weights and native CUDA libraries make recompression extremely slow.
  // Store mode keeps release builds practical; the sidecar may be deleted
  // after the application has been installed successfully.
  compression: "store",
  directories: {
    output: "release",
  },
  files: [
    "electron/**/*",
    "package.json",
    "!**/*.map",
  ],
  extraResources,
  win: {
    icon: path.join(projectRoot, "assets", "luna-icon.ico"),
    executableName: "Luna",
    target: [{ target: "nsis-web", arch: ["x64"] }],
    artifactName: "Luna-Installer-${version}.${ext}",
  },
  nsis: {
    oneClick: false,
    perMachine: false,
    allowElevation: true,
    allowToChangeInstallationDirectory: true,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
    shortcutName: "Luna",
    differentialPackage: false,
    deleteAppDataOnUninstall: false,
    installerIcon: path.join(projectRoot, "assets", "luna-icon.ico"),
    uninstallerIcon: path.join(projectRoot, "assets", "luna-icon.ico"),
  },
  nsisWeb: {
    artifactName: "Luna-Installer-${version}.${ext}",
    // Offline bundles resolve the checksum-bound package beside the installer.
    // Replace this non-routable URL only when a real private release host exists.
    appPackageUrl: "https://github.com/George-Nizor/Luna/releases/download/v0.3.0/luna-0.3.0-x64.nsis.7z",
  },
};
