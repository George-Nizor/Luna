# Luna publication audit

Audit updated: 2026-08-21. Targets: public source repository and Windows x64 release 0.3.0.

## Public source result

- The source repository is public at <https://github.com/George-Nizor/Luna>.
- Commit `161ea79` is the clean-clone packaging baseline used by the original source audit. Later
  documentation and local-install work may move `main` beyond that evidence point.
- The source-only boundary contains publishable application code and the user-owned Luna artwork.
- `.venv`, `node_modules`, builds, releases, downloaded models, runtime payloads, caches, logs,
  generated audio, and temporary snapshots are excluded.
- `assets/egirl-source-reference.wav` is ignored and must stay out of public Git history.
- The source audit found no private-key, GitHub token, OpenAI key, AWS key, or Hugging Face token
  signatures.
- Product, package, executable, installer, App ID, window, output, and data paths use the Luna 0.3.0
  identity. The retired name appears only where a cleanup test or migration note needs it.
- MIT covers user-owned source. Third-party software, models, and recordings keep their own terms.

## Dependency and asset review

The packaged runtime includes MIT, BSD, Apache, and MPL-2.0 software. FFmpeg obligations depend on the
exact binary and build configuration. A release build needs a locked transitive inventory and the
corresponding notices.

The offline payload is not cleared for public redistribution. Before publishing it, record
licence or ownership evidence for:

- the David Attenborough reference recording and XTTS fine-tune;
- the E-Girl RVC model and fixed source recording;
- Qwen model weights and required notices;
- RVC base assets;
- the packaged FFmpeg binary and build configuration;
- every downloaded archive and runtime binary.

An asset without redistribution evidence must be removed from the public payload or acquired locally
by the user. Owning this repository does not change the licence on somebody else's recording.

## Verification evidence

- The Windows backend, UI, identity, and payload suite passed during the 0.3.0 source audit.
- A fresh WSL clone passed the portable tests with the Windows-only release check skipped.
- `uv build` produced an installable wheel and source distribution from that clone.
- Multipart fixtures rebuilt and SHA-256 verified the complete payload.
- Installer metadata, App ID, output/data locations, and source exclusions have automated coverage.

Run the current `npm test` before using these points as release evidence; test counts age badly.

## Release status

The public source repository exists. No cleared Luna 0.3.0 payload release is claimed by this audit.
Publishing an asset-less stable release would make Instrumenta discover an installer it cannot use.

A verified local 0.3.0 installation can still be registered and launched by Instrumenta. That local
fact does not clear redistribution. Public release requires the evidence above, a complete Windows
payload build, resume/retry/free-space/corruption checks, clean install/uninstall verification, a
fresh public download, and checksum verification.
