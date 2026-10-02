"use strict";

const fs = require("node:fs");
const path = require("node:path");

// The renderer sends only an output UUID. It never controls filesystem paths.
function resolveOutputFile(root, id) {
  if (Array.isArray(root)) {
    for (const directory of root) {
      if (typeof id === "string" && /^[0-9a-f-]{36}$/i.test(id) && fs.existsSync(path.join(directory, id))) {
        return resolveOutputFile(directory, id);
      }
    }
    throw new Error("Generated audio is not available in a registered output folder.");
  }
  if (typeof id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error("Invalid output ID.");
  }
  const resolvedRoot = fs.realpathSync(root);
  const directory = path.join(resolvedRoot, id);
  const realDirectory = fs.realpathSync(directory);
  const relative = path.relative(resolvedRoot, realDirectory);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative) || fs.lstatSync(directory).isSymbolicLink()) {
    throw new Error("Output directory must be inside Luna's output folder.");
  }
  const audio = path.join(realDirectory, "output.wav");
  const resolvedAudio = fs.realpathSync(audio);
  if (path.dirname(resolvedAudio) !== realDirectory || fs.lstatSync(audio).isSymbolicLink() || !fs.statSync(audio).isFile()) {
    throw new Error("Generated audio is not available.");
  }
  const metadataPath = path.join(realDirectory, "metadata.json");
  if (fs.lstatSync(metadataPath).isSymbolicLink() || path.dirname(fs.realpathSync(metadataPath)) !== realDirectory) {
    throw new Error("Output metadata must be inside its generation folder.");
  }
  const metadata = JSON.parse(fs.readFileSync(metadataPath, "utf8"));
  const voice = String(metadata.profile_name || "voice").replace(/[^a-z0-9._-]+/gi, "_").slice(0, 80);
  return { audio: resolvedAudio, suggestedName: voice + "_" + id.slice(0, 8) + ".wav" };
}

module.exports = { resolveOutputFile };
