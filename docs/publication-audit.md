# Luna publication audit

Audit updated: 2026-08-21. Targets: public source repository and Windows x64 release 0.3.0.

## Public source result

- The source repository is public at <https://github.com/George-Nizor/Luna>.
- Public `main` is clean at commit `161ea79` after clean-clone packaging fixes.
- The source-only boundary contains 66 publishable files; the only file above 1 MiB is the
  user-owned Luna icon source.
- `.venv`, `node_modules`, builds, releases, downloaded models, runtime payload, caches, logs,
  generated audio, and temporary snapshots are excluded.
- `assets/egirl-source-reference.wav` is explicitly ignored and must never enter public Git history.
- Secret signature scans found no private-key, GitHub token, OpenAI key, AWS key, or Hugging Face
  token signatures and no suspect secret filenames.
- Identity checks confirm that product, package, executable, installer, App ID, window, output, and
  data paths use Luna 0.3.0. Old identity text exists only in negative clean-reinstall tests/docs.
- MIT covers user-owned source only; third-party software, models, and recordings retain their terms.

## Dependency and asset review

Source/runtime dependencies include MIT/BSD/Apache components, Coqui TTS under MPL-2.0, and FFmpeg
whose obligations depend on the exact packaged binary. Release builders must generate and preserve
an exact transitive license inventory from the locked environment.

The offline payload is not cleared for public redistribution. Before release publication, record
license/ownership evidence for:

- the David Attenborough reference recording and XTTS fine-tune;
- the E-Girl RVC model and the replacement fixed source recording;
- Qwen model weights and their required notices;
- RVC base assets;
- the packaged FFmpeg binary and its build configuration; and
- all downloaded model archives and runtime binaries.

If any recording or model cannot be redistributed, exclude it and require a user-supplied/local
acquisition step. Project ownership does not by itself grant redistribution rights to third-party
recordings, model weights, or runtime binaries.

## Verification evidence

- Windows backend/UI/identity/payload suite: 21 passing; Ruff passing.
- Fresh WSL clone: 20 passing and one Windows-only release test skipped.
- `uv build` produces an installable wheel and source distribution from the clean clone and includes
  Luna's packaged templates/static UI.
- Multipart fixtures reconstruct and SHA-256 verify their complete payload.
- Installer metadata, App ID, output/data locations, and source exclusions are tested.

## Release status

No Luna 0.3.0 GitHub Release or stable tag has been published. Publishing an asset-less release would
make Instrumenta discover an unusable desktop release, so source publication and payload publication
remain deliberately separate.

The remaining release gates are the payload redistribution evidence above, a complete Windows payload
build, resume/retry/free-space/corruption tests, clean install/uninstall verification, public release
download, and checksum verification. Until those gates pass, preserve the current Luna Voice Studio
installation and the legacy Windows source checkout as recovery inputs.
