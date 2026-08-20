# Luna

Luna is a self-contained Windows Electron application for local GPU voice generation. It includes its private Python runtime, CUDA-enabled ML packages, Qwen models, the David Attenborough XTTS model, the E-Girl RVC model, and the RVC base assets. It does not depend on ChatGPT, Codex, a terminal, a separately installed Python, or an external web browser.

The application runs its backend only on `127.0.0.1` and displays it inside a hardened Electron window. Text, reference audio, voice profiles, and generated WAV files remain on the computer. No model is loaded onto the GPU during application startup.

## Install

The offline distribution is in `release\nsis-web` and has two required files:

- `Luna-Installer-0.3.0.exe`
- `luna-0.3.0-x64.nsis.7z` (reassembled from the published `.partNNN` assets)
- `instrumenta-release.json`, containing sizes and SHA-256 digests for the installer and every chunk

`npm run dist` prepares uploadable assets under `release\\publish\\v0.3.0`. Instrumenta downloads each chunk with resume support, verifies it, reassembles the original NSIS sidecar, verifies the complete sidecar, and only then launches the installer.

Keep those files in the same directory, run the installer EXE, and choose an installation directory. The sidecar archive is checksum-bound to that installer and supplies the large offline runtime. After Luna has installed and launched successfully, both distribution files can be deleted or moved to backup storage. The installed product is launched through `Luna.exe`, its Start menu entry, or its desktop shortcut.

This is an installer bundle rather than a single self-extracting EXE because the complete installed payload is about 15 GB and exceeds the practical archive limit of a monolithic NSIS executable. Allow additional free space while installing. Another Windows x64 machine still needs a compatible NVIDIA GPU and current NVIDIA driver; the application runtime and models themselves are included.

## Use

The default output directory is `%USERPROFILE%\Documents\Luna`. Open Settings inside the app to view, open, or change it. Changing the directory restarts only the lightweight local backend; no model is loaded until the next generation request.

The voice selector contains only voices:

- **David Attenborough**: one fixed XTTS v2 fine-tune using its included `ref.wav`; no voice profile is required. The source repository supplies one checkpoint, so Quality is locked to its single configured Best path rather than presenting a fake Fast variant.
- **E-Girl**: converts a clean fixed female source with the E-Girl RVC V2 checkpoint; no voice profile is required. Quality Fast uses `Qwen/Qwen3-TTS-12Hz-0.6B-Base` as the source engine and Best uses `Qwen/Qwen3-TTS-12Hz-1.7B-Base`.
- **Saved profile names**: each user-created voice profile appears as its own voice. Fast and Best select the same 0.6B and 1.7B Qwen source engines respectively.

E-Girl uses RMVPE, female pitch `0`, index rate `0.6`, filter radius `3`, resampling disabled, RMS mix `0.25`, and protect `0.5`. Qwen Fast and Qwen Best are engines behind Quality, not voices, so they are not listed in the voice selector.

The expandable history panel shows previous sounds, selected model, and duration. A history row can load and play its WAV in the main player. While a sound is generating, the player is disabled and its play control becomes a three-dot pending animation.

Use only voices and recordings you have permission to use.

## Resource lifecycle

Electron starts one hidden private backend when Luna opens. Qwen, XTTS, and RVC workers are separate processes and are created only after generation is requested. The active worker exits when Unload Model is used, after `WORKER_IDLE_SECONDS`, or during application shutdown. Closing the Luna window requests a clean backend shutdown and uses a bounded process-termination fallback if a child does not exit.

Installed user state is kept outside the application directory:

- Settings and runtime data: `%APPDATA%\Luna`
- Backend log: `%APPDATA%\Luna\logs\desktop-backend.log`
- Generated WAV files: the output directory selected in Luna

This keeps application upgrades separate from user audio. Uninstalling Luna does not silently delete generated output or application data.

## Development

Development is intentionally separate from normal use. From the source directory:

```powershell
.\scripts\setup_dev.ps1
npm start
```

Useful commands:

```powershell
npm test       # pytest, Ruff, and JavaScript syntax checks
npm run pack   # unpacked desktop build for local testing
npm run dist   # complete offline installer bundle
```

The development model registry can download only the fixed sources committed in `scripts\download_models.ps1`:

```powershell
.\scripts\download_models.ps1 -Model david
.\scripts\download_models.ps1 -Model egirl
.\scripts\download_models.ps1 -Model qwen-fast
.\scripts\download_models.ps1 -Model qwen-best
.\scripts\download_models.ps1 -All
```

Downloads are resumable where the source supports HTTP range requests. The David archive is SHA-256 verified before extraction. No arbitrary model URL is accepted by the application or download script.

The build script creates temporary hard-linked, flattened Qwen snapshots so Electron Builder does not mispackage Hugging Face cache links. Those temporary links are removed at the end of each build. Source model caches, virtual environments, `node_modules`, generated audio, logs, and release artifacts are ignored by Git. Publish installers and verified payload chunks through GitHub Releases, never normal Git history.

## Documentation

- [`docs/identity-and-data.md`](docs/identity-and-data.md) defines the Luna identity, clean reinstall,
  registry/shortcut boundaries, and user-owned data locations.
- [`docs/releasing.md`](docs/releasing.md) covers source-only publication, asset licensing, multipart
  assembly, checksums, GitHub Release creation, and clean-machine verification.

## Troubleshooting

- If Luna reports an incomplete runtime, reinstall with the matching EXE and `.nsis.7z` sidecar beside each other.
- If generation reports CUDA unavailable, update the NVIDIA driver and confirm the target computer has a compatible NVIDIA GPU.
- If the app closes unexpectedly, inspect `%APPDATA%\Luna\logs\desktop-backend.log`.
- If a model remains resident after generation, use Unload Model. Closing Luna also terminates the worker and backend.
- If an output will not play, confirm the chosen output directory still exists and has not been moved outside Luna.

## Model sources

- David Attenborough XTTS: <https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune>
- E-Girl RVC V2: <https://voice-models.com/model/1uZvOaYhqJv>
- Qwen Fast: <https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base>
- Qwen Best: <https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base>
