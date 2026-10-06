const path = require("node:path");

const projectRoot = __dirname;
const version = require("./package.json").version;

// scripts/build_installer.ps1 downloads uv (pinned by SHA-256) and names its folder here.
const uvDirectory = process.env.LUNA_UV_DIRECTORY ? path.resolve(process.env.LUNA_UV_DIRECTORY) : "";

const extraResources = [
  {
    from: path.join(projectRoot, "app"),
    to: "backend/app",
    filter: ["**/*", "!**/__pycache__/**", "!**/*.pyc"],
  },
  { from: path.join(projectRoot, "run.py"), to: "backend/run.py" },
  // What Luna's first-run setup installs from (electron/runtime-setup.cjs). No Python runtime ships.
  {
    from: path.join(projectRoot, "packaging", "runtime"),
    to: "runtime",
    filter: ["runtime-lock.json", "apply_patches.py", "verify_runtime.py", "wheels/*.whl"],
  },
  ...(uvDirectory ? [{ from: uvDirectory, to: "runtime/uv", filter: ["uv.exe", "LICENSE-MIT", "LICENSE-APACHE"] }] : []),
  { from: path.join(projectRoot, "LICENSE"), to: "LICENSE.txt" },
  { from: path.join(projectRoot, "THIRD_PARTY_NOTICES.md"), to: "THIRD_PARTY_NOTICES.md" },
  { from: path.join(projectRoot, "assets", "luna-icon.png"), to: "assets/luna-icon.png" },
];

module.exports = {
  appId: "com.instrumenta.luna",
  productName: "Luna",
  copyright: "Copyright © 2026",
  asar: true,
  // The package is the app alone now (no Python, no CUDA libraries), so it compresses normally.
  compression: "normal",
  directories: {
    output: "release",
    buildResources: "packaging",
  },
  files: [
    "electron/**/*",
    // The setup screen is drawn with the brand v2 stylesheet and fonts before the backend exists.
    "app/static/styles.css",
    "app/static/brand/**/*",
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
    include: path.join(projectRoot, "packaging", "installer.nsh"),
    oneClick: false,
    perMachine: false,
    allowElevation: true,
    allowToChangeInstallationDirectory: true,
    createDesktopShortcut: true,
    createStartMenuShortcut: true,
    shortcutName: "Luna",
    // Instrumenta reads the installed version from this record: "Luna <version>" plus DisplayVersion.
    uninstallDisplayName: "${productName} ${version}",
    differentialPackage: false,
    deleteAppDataOnUninstall: false,
    installerIcon: path.join(projectRoot, "assets", "luna-icon.ico"),
    uninstallerIcon: path.join(projectRoot, "assets", "luna-icon.ico"),
  },
  nsisWeb: {
    artifactName: "Luna-Installer-${version}.${ext}",
    // The installer uses the package beside it when present (Instrumenta puts it there) and otherwise
    // downloads this release asset, so the installer alone is also a complete download.
    appPackageUrl: `https://github.com/George-Nizor/Luna/releases/download/v${version}/luna-${version}-x64.nsis.7z`,
  },
};
