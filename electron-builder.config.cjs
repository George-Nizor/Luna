const path = require("node:path");

const projectRoot = __dirname;
const pythonBase = process.env.VOICE_STUDIO_PYTHON_BASE;
if (!pythonBase) {
  throw new Error("VOICE_STUDIO_PYTHON_BASE must point to the portable Python base directory.");
}

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
  extraResources: [
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
    {
      from: path.join(projectRoot, ".venv", "Lib", "site-packages"),
      to: "python/Lib/site-packages",
      filter: [
        "**/*",
        "!**/__pycache__/**",
        "!**/*.pyc",
        "!**/*.pyo",
        "!**/tests/**",
        "!**/test/**",
      ],
    },
    {
      from: path.join(projectRoot, "data", "models"),
      to: "model-data/models",
      filter: ["**/*", "!.gitkeep"],
    },
    { from: path.join(projectRoot, "build", "model-payload"), to: "model-data/qwen", filter: ["**/*"] },
    { from: path.join(projectRoot, "assets", "luna-icon.png"), to: "assets/luna-icon.png" },
  ],
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
