# Luna publication audit

Audit date: 2026-08-20. Targets: public source repository and Windows x64 release 0.3.0.

## Source repository result

- Source-only boundary contains 66 publishable files; the only file above 1 MiB is the user-owned
  Luna icon source.
- `.venv`, `node_modules`, builds, releases, downloaded models, runtime payload, caches, logs,
  generated audio, and temporary snapshots are excluded.
- `assets/egirl-source-reference.wav` is explicitly ignored and must never enter public Git history.
- Secret signature scan found no private-key, GitHub token, OpenAI key, AWS key, or Hugging Face token
  signatures, and no suspect secret filenames.
- Identity audit confirms product, package, executable, installer, App ID, window, output, and data
  paths use Luna 0.3.0. Old identity text exists only in negative clean-reinstall tests/docs.
- MIT covers user-owned source only; third-party software, models, and recordings retain their terms.

The source repository is technically suitable for public review after an exact staged-diff review and
clean-clone verification.

## Dependency and asset review

Source/runtime dependencies include MIT/BSD/Apache components, Coqui TTS under MPL-2.0, and FFmpeg
whose obligations depend on the exact packaged binary. Release builders must generate and preserve
an exact transitive license inventory from the locked environment.

The offline payload is not yet cleared for public redistribution. Before release publication, record
license/ownership evidence for:

- the David Attenborough reference recording and XTTS fine-tune;
- the E-Girl RVC model and the replacement fixed source recording;
- Qwen model weights and their required notices;
- RVC base assets;
- the packaged FFmpeg binary and its build configuration; and
- all downloaded model archives and runtime binaries.

If any recording or model cannot be redistributed, exclude it and require a user-supplied/local
acquisition step. Do not infer permission from technical availability.

## Verification evidence

- Backend/UI/identity/payload suite: 20 passing.
- Multipart fixture reconstructs and SHA-256 verifies the complete payload.
- Installer metadata, App ID, output/data locations, and source exclusions are tested.

## Remaining publication gates

Approve staging and commit separately, perform a clean clone, re-run tests/audits, create and approve
the GitHub repository/push, build the complete payload only after the asset rights review, test
resume/retry/free-space/corruption and clean reinstall on Windows, download the public release, verify
all checksums, and record the final tag and chunk inventory. Public payload publication remains
blocked until the redistribution evidence above is complete.