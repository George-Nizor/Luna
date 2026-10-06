"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const { RuntimeManager, SetupCancelled, detectNvidiaGpu, lastJson, validateLock } = require("../electron/runtime-setup.cjs");

const sha256 = (data) => crypto.createHash("sha256").update(data).digest("hex");

// A wheel server that honours Range, counts requests and can be told to corrupt a file.
function wheelServer(files) {
  const requests = [];
  const server = http.createServer((request, response) => {
    const name = decodeURIComponent(request.url.slice(1));
    requests.push({ name, range: request.headers.range || "" });
    const body = files[name];
    if (!body) { response.writeHead(404); response.end(); return; }
    const range = /bytes=(\d+)-/.exec(request.headers.range || "");
    if (range) {
      const start = Number(range[1]);
      response.writeHead(206, { "Content-Range": `bytes ${start}-${body.length - 1}/${body.length}`, "Content-Length": body.length - start });
      response.end(body.subarray(start));
      return;
    }
    response.writeHead(200, { "Content-Length": body.length });
    response.end(body);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, requests, base: `http://127.0.0.1:${server.address().port}/` })));
}

// Stands in for uv and the runtime's interpreter: records each call and creates what the real one would.
function fakeSpawn(calls, { verification = { problems: [], cuda: true, device: "Test GPU" } } = {}) {
  return (file, args) => {
    calls.push([path.basename(file), ...args]);
    const child = new EventEmitter();
    child.stdout = new PassThrough();
    child.stderr = new PassThrough();
    child.kill = () => {};
    setImmediate(() => {
      if (args[0] === "venv") {
        const environment = args[args.length - 1];
        fs.mkdirSync(path.join(environment, "Scripts"), { recursive: true });
        fs.writeFileSync(path.join(environment, "Scripts", "python.exe"), "");
      }
      if (args.some((arg) => arg.endsWith("apply_patches.py"))) child.stdout.write("[]\n");
      if (args.some((arg) => arg.endsWith("verify_runtime.py"))) child.stdout.write(`banner\n${JSON.stringify({ python: "3.12.15", ...verification })}\n`);
      child.stdout.end();
      child.stderr.end();
      child.emit("close", 0);
    });
    return child;
  };
}

function fixture(base, wheels, lockHash = "0123456789abcdef") {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "luna-runtime-"));
  const resources = path.join(root, "resources");
  fs.mkdirSync(path.join(resources, "wheels"), { recursive: true });
  const bundled = Buffer.from("bundled wheel");
  fs.writeFileSync(path.join(resources, "wheels", "local-1.0-py3-none-any.whl"), bundled);
  const packages = Object.entries(wheels).map(([file, body]) => ({
    name: file.split("-")[0], version: "1.0", file, sha256: sha256(body), url: `${base}${file}`, size: body.length,
  }));
  packages.push({ name: "local", version: "1.0", file: "local-1.0-py3-none-any.whl", sha256: sha256(bundled), bundled: "wheels/local-1.0-py3-none-any.whl", size: bundled.length });
  const lock = { schemaVersion: 1, lockHash, platform: "windows-x64", python: "3.12.15", uv: "0.12.23", downloadBytes: Object.values(wheels).reduce((sum, body) => sum + body.length, 0), packages };
  fs.writeFileSync(path.join(resources, "runtime-lock.json"), JSON.stringify(lock));
  return { root, resources, runtimeRoot: path.join(root, "runtime"), lock };
}

test("the lock is validated before anything is downloaded", () => {
  assert.throws(() => validateLock({ schemaVersion: 1, lockHash: "nothex", python: "3.12.15", packages: [{}] }));
  const entry = { name: "a", version: "1", file: "a-1-py3-none-any.whl", sha256: "0".repeat(64), size: 1 };
  assert.throws(() => validateLock({ schemaVersion: 1, lockHash: "0123456789abcdef", python: "3.12.15", packages: [{ ...entry, url: "http://example.com/a.whl" }] }), /HTTPS/);
  assert.throws(() => validateLock({ schemaVersion: 1, lockHash: "0123456789abcdef", python: "3.12.15", packages: [{ ...entry, file: "../a.whl", url: "https://example.com/a.whl" }] }));
  assert.throws(() => validateLock({ schemaVersion: 1, lockHash: "0123456789abcdef", python: "3.13.0", packages: [{ ...entry, url: "https://example.com/a.whl" }] }));
  assert.ok(validateLock({ schemaVersion: 1, lockHash: "0123456789abcdef", python: "3.12.15", packages: [{ ...entry, url: "https://example.com/a.whl" }] }));
});

test("lastJson finds the result after library banners", () => {
  assert.deepEqual(lastJson("flash-attn is not installed\n{\"cuda\": true}\n"), { cuda: true });
  assert.equal(lastJson("no json here"), null);
});

test("first setup resumes a partial download, installs, verifies and switches in one step", async () => {
  const wheels = { "big-1.0-py3-none-any.whl": crypto.randomBytes(300_000), "small-1.0-py3-none-any.whl": Buffer.from("small wheel") };
  const { server, requests, base } = await wheelServer(wheels);
  const { root, resources, runtimeRoot, lock } = fixture(base, wheels);
  try {
    // An earlier run stopped after 100 kB of the big wheel.
    fs.mkdirSync(path.join(runtimeRoot, "downloads"), { recursive: true });
    fs.writeFileSync(path.join(runtimeRoot, "downloads", "big-1.0-py3-none-any.whl.partial"), wheels["big-1.0-py3-none-any.whl"].subarray(0, 100_000));
    // And an older runtime is current.
    fs.mkdirSync(path.join(runtimeRoot, "fedcba9876543210", "Scripts"), { recursive: true });
    fs.writeFileSync(path.join(runtimeRoot, "current.json"), JSON.stringify({ lockHash: "fedcba9876543210" }));

    const calls = [];
    const manager = new RuntimeManager({ allowLoopbackHttp: true, resources, uv: "uv.exe", root: runtimeRoot, backendRoot: root, spawn: fakeSpawn(calls), platform: "win32" });
    assert.equal(manager.ready(), null);
    const summary = manager.summary();
    assert.equal(summary.alreadyDownloaded, 100_000);
    assert.equal(summary.replacing, "fedcba9876543210");

    const phases = new Set();
    manager.on("progress", (update) => phases.add(update.phase));
    const result = await manager.run();

    assert.deepEqual(requests.find((r) => r.name === "big-1.0-py3-none-any.whl"), { name: "big-1.0-py3-none-any.whl", range: "bytes=100000-" });
    assert.deepEqual([...phases].filter((phase) => phase !== "log"), ["python", "download", "install", "verify", "cleanup", "done"]);
    assert.equal(result.lockHash, lock.lockHash);
    assert.equal(result.python, path.join(runtimeRoot, lock.lockHash, "Scripts", "python.exe"));
    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(runtimeRoot, "current.json"), "utf8")).lockHash, lock.lockHash);
    assert.ok(manager.ready());

    const sync = calls.find((call) => call[1] === "pip");
    assert.ok(sync.includes("--require-hashes") && sync.includes("--offline") && sync.includes("--no-index") && sync.includes("--no-build"));
    assert.ok(calls.find((call) => call[1] === "python" && call[2] === "install" && call[3] === "3.12.15"));
    // The old runtime, the downloads and the requirements file are gone; the new runtime stays.
    assert.deepEqual(fs.readdirSync(runtimeRoot).sort(), [lock.lockHash, "current.json"].sort());
    const marker = JSON.parse(fs.readFileSync(path.join(runtimeRoot, lock.lockHash, "luna-runtime.json"), "utf8"));
    assert.equal(marker.verification.cuda, true);

    // A second start finds it ready and starts nothing.
    const again = [];
    const second = new RuntimeManager({ allowLoopbackHttp: true, resources, uv: "uv.exe", root: runtimeRoot, backendRoot: root, spawn: fakeSpawn(again), platform: "win32" });
    assert.ok(second.ready());
    assert.equal(again.length, 0);
  } finally {
    server.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("a corrupt download is refused and nothing is switched", async () => {
  const wheels = { "good-1.0-py3-none-any.whl": Buffer.from("good") };
  const { server, base } = await wheelServer({ "good-1.0-py3-none-any.whl": Buffer.from("evil") });
  const { root, resources, runtimeRoot } = fixture(base, wheels);
  try {
    const calls = [];
    const manager = new RuntimeManager({ allowLoopbackHttp: true, resources, uv: "uv.exe", root: runtimeRoot, backendRoot: root, spawn: fakeSpawn(calls), platform: "win32" });
    // Keep the retry back-off short for the test.
    const realTimeout = global.setTimeout;
    global.setTimeout = (fn, _ms, ...args) => realTimeout(fn, 0, ...args);
    try {
      await assert.rejects(manager.run(), (error) => error.code === "DOWNLOAD" && /SHA-256/.test(error.message));
    } finally { global.setTimeout = realTimeout; }
    assert.equal(manager.ready(), null);
    assert.ok(!fs.existsSync(path.join(runtimeRoot, "current.json")));
    assert.ok(!calls.some((call) => call[1] === "venv"));
  } finally {
    server.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("a runtime that fails its check is never switched to", async () => {
  const wheels = { "a-1.0-py3-none-any.whl": Buffer.from("a") };
  const { server, base } = await wheelServer(wheels);
  const { root, resources, runtimeRoot, lock } = fixture(base, wheels);
  try {
    const manager = new RuntimeManager({ allowLoopbackHttp: true, resources, uv: "uv.exe", root: runtimeRoot, backendRoot: root, platform: "win32",
      spawn: fakeSpawn([], { verification: { problems: ["import torch failed"] } }) });
    await assert.rejects(manager.run(), /import torch failed/);
    assert.equal(manager.ready(), null);
    assert.ok(!fs.existsSync(path.join(runtimeRoot, lock.lockHash)));
    // The download is kept for the retry.
    assert.ok(fs.existsSync(path.join(runtimeRoot, "downloads", "a-1.0-py3-none-any.whl")));
  } finally {
    server.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("cancelling stops the setup without switching anything", async () => {
  const wheels = { "a-1.0-py3-none-any.whl": Buffer.from("a") };
  const { server, base } = await wheelServer(wheels);
  const { root, resources, runtimeRoot } = fixture(base, wheels);
  try {
    let manager = null;
    const spawn = (file, args) => {
      const child = new EventEmitter();
      child.stdout = new PassThrough();
      child.stderr = new PassThrough();
      child.kill = () => { child.stdout.end(); child.stderr.end(); child.emit("close", 1); };
      if (args[0] === "python") setImmediate(() => manager.cancel());
      return child;
    };
    manager = new RuntimeManager({ allowLoopbackHttp: true, resources, uv: "uv.exe", root: runtimeRoot, backendRoot: root, spawn, platform: "win32" });
    await assert.rejects(manager.run(), SetupCancelled);
    assert.equal(manager.ready(), null);
  } finally {
    server.close();
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("the packaged app carries the runtime plan, uv and the setup screen, and no Python", () => {
  const root = path.resolve(__dirname, "..");
  process.env.LUNA_UV_DIRECTORY = path.join(root, "build", "uv-test");
  try {
    delete require.cache[require.resolve("../electron-builder.config.cjs")];
    const config = require("../electron-builder.config.cjs");
    const targets = config.extraResources.map((entry) => entry.to);
    assert.ok(targets.includes("runtime") && targets.includes("runtime/uv"));
    assert.ok(!targets.some((target) => target === "python" || target.startsWith("python/") || target.startsWith("model-data")));
    const runtime = config.extraResources.find((entry) => entry.to === "runtime");
    assert.deepEqual(runtime.filter, ["runtime-lock.json", "apply_patches.py", "verify_runtime.py", "wheels/*.whl"]);
    assert.ok(config.files.includes("app/static/styles.css"));
    assert.equal(config.nsis.uninstallDisplayName, "${productName} ${version}");
    assert.equal(config.appId, "com.instrumenta.luna");
    for (const file of ["index.html", "setup.css", "setup.js"]) assert.ok(fs.existsSync(path.join(root, "electron", "setup", file)));
  } finally {
    delete process.env.LUNA_UV_DIRECTORY;
  }
});

test("a machine without an NVIDIA driver gets a reason, not a crash", async () => {
  const missing = await detectNvidiaGpu({ execFile: (_file, _args, _options, callback) => callback(new Error("ENOENT")) });
  assert.equal(missing.found, false);
  assert.match(missing.reason, /nvidia-smi was not found/);
  const present = await detectNvidiaGpu({ execFile: (_file, _args, _options, callback) => callback(null, "NVIDIA GeForce RTX 4080 SUPER, 617.14, 16376\n") });
  assert.deepEqual(present, { found: true, name: "NVIDIA GeForce RTX 4080 SUPER", driver: "617.14", memoryMiB: 16376 });
});
