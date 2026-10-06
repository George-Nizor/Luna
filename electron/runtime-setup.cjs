"use strict";

// Luna's Python runtime, set up by Luna itself after installation.
//
// The installer carries the app, the backend source, uv and runtime-lock.json (scripts/runtime_lock.py
// writes it from packaging/runtime/uv.lock): the exact wheels, with URL, size and SHA-256, for CPython
// 3.12 on Windows x64. On first start, and whenever the lock hash changes, Luna:
//
//   1. installs the pinned CPython with `uv python install` into <root>\python;
//   2. downloads every wheel into <root>\downloads itself, resuming with HTTP Range and checking the
//      size and SHA-256 of each (so the setup screen can show real bytes and resume after a restart);
//   3. creates <root>\<lock hash>.partial with `uv venv` and installs the wheels with
//      `uv pip sync --require-hashes --offline --no-index`, so uv checks every hash a second time and
//      can neither resolve nor fetch anything the lock does not name;
//   4. applies Luna's reviewed source patches and runs verify_runtime.py with the new interpreter;
//   5. renames the folder to <root>\<lock hash>, writes its marker, then replaces current.json in one
//      rename; only after that are stale environments, downloads and uv's cache removed.
//
// Nothing here touches %APPDATA%\Luna. <root> is %LOCALAPPDATA%\Luna\runtime unless
// LUNA_RUNTIME_ROOT names another absolute folder (isolated tests).

const { spawn, execFile } = require("node:child_process");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");

const MARKER = "luna-runtime.json";
const POINTER = "current.json";
const HASH_PATTERN = /^[0-9a-f]{16}$/;
const SAFE_FILE = /^[A-Za-z0-9][A-Za-z0-9._+-]*\.whl$/;
const PARALLEL_DOWNLOADS = 4;
const DOWNLOAD_ATTEMPTS = 4;
// Installed size relative to the compressed wheels (the 0.4.1 runtime was 4.9 GB from ~3 GB).
const INSTALL_FACTOR = 1.8;
const HEADROOM = 512 * 1024 * 1024;

class SetupCancelled extends Error {
  constructor() { super("Setup was cancelled."); this.name = "SetupCancelled"; }
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
}

function writeJsonAtomic(file, value) {
  const temporary = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temporary, file);
}

function within(root, target) {
  const relative = path.relative(root, target);
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

// Tests serve wheels from a loopback HTTP server; the app never passes allowLoopbackHttp.
function validateLock(lock, { allowLoopbackHttp = false } = {}) {
  if (!lock || lock.schemaVersion !== 1 || !HASH_PATTERN.test(String(lock.lockHash))) throw new Error("runtime-lock.json is not a Luna runtime lock.");
  if (!/^3\.12\.\d+$/.test(String(lock.python))) throw new Error("runtime-lock.json names an unsupported Python.");
  if (!Array.isArray(lock.packages) || !lock.packages.length) throw new Error("runtime-lock.json lists no packages.");
  for (const entry of lock.packages) {
    if (!SAFE_FILE.test(String(entry.file)) || !/^[0-9a-f]{64}$/.test(String(entry.sha256)) || !Number.isSafeInteger(entry.size) || entry.size <= 0) {
      throw new Error(`runtime-lock.json has an invalid entry for ${entry.name}.`);
    }
    const secure = /^https:\/\//.test(entry.url) || (allowLoopbackHttp && /^http:\/\/127\.0\.0\.1:\d+\//.test(entry.url));
    if (entry.url !== undefined && !secure) throw new Error(`${entry.name} is not downloaded over HTTPS.`);
    if (entry.url === undefined && !/^wheels\/[A-Za-z0-9._+-]+\.whl$/.test(String(entry.bundled))) throw new Error(`${entry.name} has no source.`);
  }
  return lock;
}

// Windows can hold a folder briefly after the processes inside it exit (antivirus scans, the
// interpreter's own handles), so a rename that fails with EPERM/EBUSY is tried again for a while.
async function renameWithRetry(from, to, attempts = 40) {
  for (let attempt = 1; ; attempt += 1) {
    try {
      fs.renameSync(from, to);
      return;
    } catch (error) {
      if (attempt >= attempts || !["EPERM", "EBUSY", "EACCES"].includes(error.code)) throw error;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
}

function sha256File(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    fs.createReadStream(file).on("error", reject).on("data", (chunk) => hash.update(chunk)).on("end", () => resolve(hash.digest("hex")));
  });
}

function fileSize(file) {
  try { return fs.statSync(file).size; } catch { return 0; }
}

function freeBytes(directory) {
  try {
    const stats = fs.statfsSync(directory);
    return Number(stats.bavail) * Number(stats.bsize);
  } catch {
    return Infinity;
  }
}

function formatBytes(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} KB`;
}

// The last line of output that parses as a JSON object (libraries print banners on stdout).
function lastJson(text) {
  const lines = String(text).trim().split(/\r?\n/).reverse();
  for (const line of lines) {
    if (!line.trim().startsWith("{")) continue;
    try { return JSON.parse(line); } catch { /* keep looking */ }
  }
  return null;
}

/** Ask the NVIDIA driver which GPU is present. Never throws. */
function detectNvidiaGpu(options = {}) {
  const run = options.execFile || execFile;
  const candidates = [
    "nvidia-smi.exe",
    path.join(process.env.SystemRoot || "C:\\Windows", "System32", "nvidia-smi.exe"),
    path.join(process.env.ProgramW6432 || "C:\\Program Files", "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe"),
  ];
  return new Promise((resolve) => {
    const attempt = (index) => {
      if (index >= candidates.length) {
        resolve({ found: false, reason: "No NVIDIA driver answered (nvidia-smi was not found)." });
        return;
      }
      run(candidates[index], ["--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"], { timeout: 15_000, windowsHide: true }, (error, stdout) => {
        if (error) { attempt(index + 1); return; }
        const first = String(stdout).trim().split(/\r?\n/)[0] || "";
        const [name, driver, memory] = first.split(",").map((part) => part.trim());
        if (!name) { resolve({ found: false, reason: "The NVIDIA driver reported no GPU." }); return; }
        resolve({ found: true, name, driver, memoryMiB: Number(memory) || null });
      });
    };
    attempt(0);
  });
}

class RuntimeManager extends EventEmitter {
  /**
   * @param {object} options
   * @param {string} options.resources  folder with runtime-lock.json, wheels/, apply_patches.py, verify_runtime.py
   * @param {string} options.uv         uv.exe
   * @param {string} options.root       where runtimes live
   * @param {string} options.backendRoot  Luna's backend source (for verify_runtime.py)
   * @param {Function} [options.fetch]  fetch implementation (Electron's net.fetch in the app)
   */
  constructor(options) {
    super();
    this.resources = path.resolve(options.resources);
    this.uv = options.uv;
    this.root = path.resolve(options.root);
    this.backendRoot = options.backendRoot;
    this.fetch = options.fetch || globalThis.fetch;
    this.spawn = options.spawn || spawn;
    this.platform = options.platform || process.platform;
    this.allowLoopbackHttp = Boolean(options.allowLoopbackHttp);
    this.lock = validateLock(readJson(path.join(this.resources, "runtime-lock.json")), { allowLoopbackHttp: this.allowLoopbackHttp });
    this.running = null;
    this.abort = null;
    this.children = new Set();
  }

  get downloadsDir() { return path.join(this.root, "downloads"); }
  get pythonDir() { return path.join(this.root, "python"); }
  get cacheDir() { return path.join(this.root, "cache"); }
  environmentDir(hash = this.lock.lockHash) { return path.join(this.root, hash); }

  interpreter(environment) {
    return this.platform === "win32"
      ? path.join(environment, "Scripts", "python.exe")
      : path.join(environment, "bin", "python");
  }

  /** The verified environment for this lock, or null. Cheap: no process is started. */
  ready() {
    try {
      const pointer = readJson(path.join(this.root, POINTER));
      if (pointer.lockHash !== this.lock.lockHash) return null;
      const environment = this.environmentDir();
      const marker = readJson(path.join(environment, MARKER));
      const python = this.interpreter(environment);
      if (marker.lockHash !== this.lock.lockHash || !fs.existsSync(python)) return null;
      return { lockHash: this.lock.lockHash, environment, python, verification: marker.verification || {} };
    } catch {
      return null;
    }
  }

  /** What the setup screen shows before anything starts. */
  summary() {
    const downloads = this.lock.packages.filter((entry) => entry.url);
    let have = 0;
    for (const entry of downloads) {
      const done = path.join(this.downloadsDir, entry.file);
      have += fileSize(done) === entry.size ? entry.size : Math.min(entry.size, fileSize(`${done}.partial`));
    }
    let previous = "";
    try { previous = readJson(path.join(this.root, POINTER)).lockHash || ""; } catch { /* first setup */ }
    return {
      lockHash: this.lock.lockHash,
      python: this.lock.python,
      packages: this.lock.packages.length,
      downloadBytes: this.lock.downloadBytes,
      alreadyDownloaded: have,
      installBytes: Math.round(this.lock.downloadBytes * INSTALL_FACTOR),
      root: this.root,
      replacing: previous && previous !== this.lock.lockHash ? previous : "",
      freeBytes: freeBytes(fs.existsSync(this.root) ? this.root : path.dirname(this.root)),
    };
  }

  cancel() {
    if (this.abort) this.abort.abort();
    for (const child of this.children) {
      try { child.kill(); } catch { /* already gone */ }
    }
  }

  run() {
    if (!this.running) {
      this.running = this.#setup().finally(() => { this.running = null; this.abort = null; });
    }
    return this.running;
  }

  #progress(update) {
    this.emit("progress", update);
  }

  #checkCancelled() {
    if (this.abort?.signal.aborted) throw new SetupCancelled();
  }

  async #setup() {
    this.abort = new AbortController();
    fs.mkdirSync(this.downloadsDir, { recursive: true });
    const summary = this.summary();
    const needed = (summary.downloadBytes - summary.alreadyDownloaded) + summary.installBytes + HEADROOM;
    if (summary.freeBytes < needed) {
      const error = new Error(`Luna needs about ${formatBytes(needed)} free on the drive holding ${this.root}; ${formatBytes(summary.freeBytes)} is free.`);
      error.code = "DISK_SPACE";
      throw error;
    }

    this.#progress({ phase: "python", message: `Installing Python ${this.lock.python}` });
    await this.#uv(["python", "install", this.lock.python], { UV_PYTHON_DOWNLOADS: "automatic" });
    this.#checkCancelled();

    await this.#downloadAll();
    this.#checkCancelled();

    const staging = `${this.environmentDir()}.partial`;
    fs.rmSync(staging, { recursive: true, force: true });
    this.#progress({ phase: "install", message: `Installing ${this.lock.packages.length} packages` });
    await this.#uv(["venv", "--relocatable", "--python", this.lock.python, staging]);
    const requirements = path.join(this.root, `requirements-${this.lock.lockHash}.txt`);
    fs.writeFileSync(requirements, this.lock.packages.map((entry) => `${entry.name}==${entry.version} --hash=sha256:${entry.sha256}`).join("\n") + "\n", "utf8");
    await this.#uv([
      "pip", "sync", requirements,
      "--python", this.interpreter(staging),
      "--require-hashes", "--offline", "--no-index", "--no-build",
      "--find-links", this.downloadsDir,
      "--find-links", path.join(this.resources, "wheels"),
    ]);
    this.#checkCancelled();

    this.#progress({ phase: "verify", message: "Checking the new runtime" });
    const sitePackages = this.platform === "win32" ? path.join(staging, "Lib", "site-packages") : null;
    const patches = await this.#python(staging, [path.join(this.resources, "apply_patches.py"), sitePackages || this.#posixSitePackages(staging)]);
    const verification = lastJson((await this.#python(staging, [path.join(this.resources, "verify_runtime.py"), path.join(this.resources, "runtime-lock.json"), this.backendRoot], { allowFailure: true })).stdout);
    if (!verification) throw new Error("The new runtime could not be checked: verify_runtime.py printed no result.");
    if (verification.problems?.length) throw new Error(`The new runtime failed its check:\n${verification.problems.join("\n")}`);
    this.#checkCancelled();

    // Switch: the folder only gets its final name once complete, and current.json changes in one rename.
    const environment = this.environmentDir();
    fs.rmSync(environment, { recursive: true, force: true });
    await renameWithRetry(staging, environment);
    writeJsonAtomic(path.join(environment, MARKER), {
      lockHash: this.lock.lockHash,
      python: this.lock.python,
      packages: this.lock.packages.length,
      patches: JSON.parse(patches.stdout),
      verification,
      installedAt: new Date().toISOString(),
    });
    writeJsonAtomic(path.join(this.root, POINTER), { lockHash: this.lock.lockHash, python: this.lock.python, switchedAt: new Date().toISOString() });
    fs.rmSync(requirements, { force: true });
    this.#progress({ phase: "cleanup", message: "Removing what is no longer needed" });
    const removed = this.prune();
    this.#progress({ phase: "done", message: "Ready" });
    return { ...this.ready(), verification, removed };
  }

  #posixSitePackages(environment) {
    const lib = path.join(environment, "lib");
    const version = fs.readdirSync(lib).find((name) => name.startsWith("python"));
    return path.join(lib, version, "site-packages");
  }

  /** Remove other environments, finished downloads, uv's cache and unreferenced Pythons. */
  prune() {
    const removed = [];
    const keep = this.lock.lockHash;
    for (const name of fs.existsSync(this.root) ? fs.readdirSync(this.root) : []) {
      const full = path.join(this.root, name);
      const environment = /^([0-9a-f]{16})(\.partial)?$/.exec(name);
      const stale = (environment && !(environment[1] === keep && !environment[2]))
        || name === "downloads" || name === "cache" || /^requirements-[0-9a-f]{16}\.txt$/.test(name);
      if (stale && within(this.root, full)) {
        fs.rmSync(full, { recursive: true, force: true });
        removed.push(name);
      }
    }
    if (fs.existsSync(this.pythonDir)) {
      for (const name of fs.readdirSync(this.pythonDir)) {
        const match = /^cpython-(\d+\.\d+\.\d+)-/.exec(name);
        if (match && match[1] !== this.lock.python) {
          fs.rmSync(path.join(this.pythonDir, name), { recursive: true, force: true });
          removed.push(`python/${name}`);
        }
      }
    }
    return removed;
  }

  async #downloadAll() {
    const entries = this.lock.packages.filter((entry) => entry.url);
    const total = entries.reduce((sum, entry) => sum + entry.size, 0);
    const progress = new Map(entries.map((entry) => [entry.file, 0]));
    const started = Date.now();
    let startedBytes = null;
    let lastEmit = 0;
    const emit = (force = false) => {
      const now = Date.now();
      if (!force && now - lastEmit < 250) return;
      lastEmit = now;
      const done = [...progress.values()].reduce((sum, value) => sum + value, 0);
      if (startedBytes === null) startedBytes = done;
      const seconds = Math.max(0.001, (now - started) / 1000);
      const rate = (done - startedBytes) / seconds;
      const active = entries.filter((entry) => progress.get(entry.file) > 0 && progress.get(entry.file) < entry.size).map((entry) => entry.name);
      this.#progress({ phase: "download", done, total, rate, eta: rate > 0 ? (total - done) / rate : null, active, message: `Downloading ${formatBytes(total)}` });
    };
    for (const entry of entries) {
      const target = path.join(this.downloadsDir, entry.file);
      progress.set(entry.file, fileSize(target) === entry.size ? entry.size : Math.min(entry.size, fileSize(`${target}.partial`)));
    }
    emit(true);
    // Largest first, so the long PyTorch download starts at once and the small ones fill around it.
    const queue = [...entries].sort((a, b) => b.size - a.size);
    const worker = async () => {
      while (queue.length) {
        this.#checkCancelled();
        const entry = queue.shift();
        await this.#download(entry, (bytes) => { progress.set(entry.file, bytes); emit(); });
      }
    };
    await Promise.all(Array.from({ length: PARALLEL_DOWNLOADS }, worker));
    emit(true);
  }

  async #download(entry, onBytes) {
    const target = path.join(this.downloadsDir, entry.file);
    const partial = `${target}.partial`;
    if (!within(this.downloadsDir, target)) throw new Error(`Refusing to write ${entry.file} outside the download folder.`);
    if (fileSize(target) === entry.size && await sha256File(target) === entry.sha256) {
      onBytes(entry.size);
      return;
    }
    fs.rmSync(target, { force: true });
    let lastError = null;
    for (let attempt = 1; attempt <= DOWNLOAD_ATTEMPTS; attempt += 1) {
      this.#checkCancelled();
      try {
        await this.#fetchInto(entry, partial, onBytes);
        if (fileSize(partial) !== entry.size) throw new Error(`${entry.file} is ${fileSize(partial)} bytes, expected ${entry.size}.`);
        if (await sha256File(partial) !== entry.sha256) {
          fs.rmSync(partial, { force: true });
          throw new Error(`${entry.file} failed its SHA-256 check and will be downloaded again.`);
        }
        await renameWithRetry(partial, target);
        onBytes(entry.size);
        return;
      } catch (error) {
        if (error instanceof SetupCancelled || this.abort?.signal.aborted) throw new SetupCancelled();
        lastError = error;
        if (fileSize(partial) > entry.size) fs.rmSync(partial, { force: true });
        if (attempt < DOWNLOAD_ATTEMPTS) await new Promise((resolve) => setTimeout(resolve, 1500 * attempt));
      }
    }
    const error = new Error(`Could not download ${entry.name} (${entry.file}): ${lastError?.message || lastError}`);
    error.code = "DOWNLOAD";
    throw error;
  }

  async #fetchInto(entry, partial, onBytes) {
    let offset = fileSize(partial);
    if (offset >= entry.size) offset = 0;
    const headers = { "User-Agent": "Luna runtime setup" };
    if (offset > 0) headers.Range = `bytes=${offset}-`;
    const response = await this.fetch(entry.url, { headers, redirect: "follow", cache: "no-store", signal: this.abort.signal });
    // Electron's net.fetch may leave Response.url empty; when it names the final URL it must be HTTPS.
    // (The content itself is trusted only after its SHA-256 matches the lock.)
    if (response.url && !response.url.startsWith("https://") && !(this.allowLoopbackHttp && response.url.startsWith("http://127.0.0.1:"))) {
      throw new Error("The download left HTTPS.");
    }
    let append = false;
    if (offset > 0 && response.status === 206) {
      const range = /bytes (\d+)-/.exec(response.headers.get("content-range") || "");
      append = range && Number(range[1]) === offset;
    } else if (response.status !== 200) {
      throw new Error(`HTTP ${response.status}`);
    }
    if (!append) offset = 0;
    const output = fs.createWriteStream(partial, { flags: append ? "a" : "w" });
    let written = offset;
    onBytes(written);
    try {
      for await (const chunk of response.body) {
        written += chunk.length;
        if (written > entry.size) throw new Error(`${entry.file} is larger than its locked size.`);
        if (!output.write(chunk)) await new Promise((resolve) => output.once("drain", resolve));
        onBytes(written);
      }
    } finally {
      await new Promise((resolve) => output.end(resolve));
    }
  }

  #env(extra = {}) {
    const env = {};
    // Nothing from the user's own Python or uv configuration reaches the runtime.
    for (const [key, value] of Object.entries(process.env)) {
      if (/^(UV_|PYTHON|VIRTUAL_ENV|CONDA)/i.test(key)) continue;
      env[key] = value;
    }
    return {
      ...env,
      UV_NO_CONFIG: "1",
      UV_CACHE_DIR: this.cacheDir,
      UV_PYTHON_INSTALL_DIR: this.pythonDir,
      UV_PYTHON_PREFERENCE: "only-managed",
      UV_PYTHON_DOWNLOADS: "never",
      UV_NO_PROGRESS: "1",
      UV_NATIVE_TLS: "1",
      PYTHONNOUSERSITE: "1",
      PYTHONUTF8: "1",
      ...extra,
    };
  }

  #exec(file, args, env, options = {}) {
    return new Promise((resolve, reject) => {
      this.#checkCancelled();
      const child = this.spawn(file, args, { env, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
      this.children.add(child);
      let stdout = "";
      let stderr = "";
      child.stdout.on("data", (data) => { stdout += data; });
      child.stderr.on("data", (data) => {
        stderr += data;
        const line = String(data).trim().split(/\r?\n/).pop();
        if (line) this.#progress({ phase: "log", line: line.slice(0, 300) });
      });
      child.on("error", (error) => { this.children.delete(child); reject(error); });
      child.on("close", (code) => {
        this.children.delete(child);
        if (this.abort?.signal.aborted) { reject(new SetupCancelled()); return; }
        if (code === 0 || options.allowFailure) { resolve({ code, stdout, stderr }); return; }
        const tail = (stderr || stdout).trim().split(/\r?\n/).slice(-12).join("\n");
        reject(new Error(`${path.basename(file)} ${args.slice(0, 2).join(" ")} failed (exit ${code}).\n${tail}`));
      });
    });
  }

  #uv(args, extra = {}) {
    return this.#exec(this.uv, args, this.#env(extra));
  }

  #python(environment, args, options = {}) {
    return this.#exec(this.interpreter(environment), ["-I", ...args], this.#env(), options);
  }
}

module.exports = { RuntimeManager, SetupCancelled, detectNvidiaGpu, formatBytes, lastJson, validateLock };
