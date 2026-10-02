"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { resolveOutputFile } = require("../electron/output-files.cjs");

test("desktop actions accept only existing output UUIDs within the output folder", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "luna-output-"));
  const id = "00000000-0000-4000-8000-000000000001";
  try {
    const folder = path.join(root, id); fs.mkdirSync(folder);
    fs.writeFileSync(path.join(folder, "output.wav"), "audio");
    fs.writeFileSync(path.join(folder, "metadata.json"), JSON.stringify({ profile_name: "../Ryan" }));
    const output = resolveOutputFile(root, id);
    assert.equal(output.audio, fs.realpathSync(path.join(folder, "output.wav")));
    assert(!output.suggestedName.includes("/"));
    assert.throws(() => resolveOutputFile(root, "../secret"));
    assert.throws(() => resolveOutputFile(root, "https://example.com/file"));
    fs.unlinkSync(path.join(folder, "output.wav"));
    assert.throws(() => resolveOutputFile(root, id));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test("packaging starts without preinstalled weights and includes the curated manifest", () => {
  const root = path.resolve(__dirname, "..");
  const main = fs.readFileSync(path.join(root, "electron/main.cjs"), "utf8");
  assert(!main.includes("requiredPaths.push(paths.qwenFast"));
  const previous = process.env.LUNA_INSTALLED_PAYLOAD_ROOT;
  process.env.LUNA_INSTALLED_PAYLOAD_ROOT = root;
  process.env.LUNA_INCLUDE_BUNDLED_MODELS = "false";
  try {
    const config = require("../electron-builder.config.cjs");
    assert(!config.extraResources.some((entry) => entry.to.startsWith("model-data/")));
    assert(config.extraResources.some((entry) => entry.to === "backend/app"));
  } finally {
    if (previous === undefined) delete process.env.LUNA_INSTALLED_PAYLOAD_ROOT;
    else process.env.LUNA_INSTALLED_PAYLOAD_ROOT = previous;
    delete process.env.LUNA_INCLUDE_BUNDLED_MODELS;
  }
});
