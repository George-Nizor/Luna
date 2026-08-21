![Luna banner](docs/images/luna-banner.png)

# Luna

Luna is a Windows desktop app for generating speech with local GPU models. It carries its own Python
runtime and opens a private backend inside a hardened Electron window. Text, reference audio, voice
profiles, and generated WAV files stay on the computer.

Current version: **0.3.0**.

## Open it

Use the Luna card in Instrumenta, the Start menu entry, or `Luna.exe`. Instrumenta treats Luna as an
installed desktop application: it checks the Windows installation record and launches the registered
executable.

Choose a voice, enter the text, select Fast or Best when the voice supports both, then generate. The
history drawer keeps previous sounds available for replay.

Models load after the first generation request. Use **Unload model** when GPU memory is needed
elsewhere.

## Voices

- **David Attenborough** uses the configured XTTS v2 fine-tune and its fixed reference recording. The
  source provides one checkpoint, so the quality control stays on its real single path.
- **E-Girl** generates a clean source with Qwen, then applies the E-Girl RVC V2 conversion. Fast uses
  Qwen 0.6B; Best uses Qwen 1.7B.
- **Saved profiles** use a user-created reference voice. Fast and Best select the same Qwen engines.

Qwen models are generation engines, so they do not appear as pretend voices in the voice list.

Use voices and recordings you have permission to use.

## Output and local data

The default output folder is:

```text
%USERPROFILE%\Documents\Luna
```

Settings can open or change it. A folder change restarts the lightweight backend and leaves the model
unloaded until the next job.

Other state lives here:

```text
Settings and runtime data  %APPDATA%\Luna
Backend log                %APPDATA%\Luna\logs\desktop-backend.log
Generated audio            the output folder selected in Luna
```

Uninstalling the application leaves generated audio and user settings in place. Delete them manually
only when they are no longer wanted.

## The offline payload

A complete local installation is roughly 15 GB because it contains CUDA-enabled packages, voice
models, and RVC assets. They have shown no interest in becoming a polite little installer.

The distribution uses these files:

```text
Luna-Installer-0.3.0.exe
luna-0.3.0-x64.nsis.7z
instrumenta-release.json
```

GitHub upload builds split the sidecar into numbered parts below the per-asset size limit. Instrumenta
resumes individual downloads, checks free space, verifies every part, rebuilds the sidecar, verifies
the complete file, and then starts the installer.

The installer and sidecar must be from the same build and sit in the same folder for a manual
installation. Once Luna is installed and opens correctly, those distribution files can be removed.

## Process lifecycle

Electron starts one loopback backend on `127.0.0.1`. Qwen, XTTS, and RVC run as separate workers.
Only the active model worker occupies GPU memory.

The worker exits after the configured idle timeout, when **Unload model** is pressed, or when Luna
closes. Shutdown first asks each process to exit cleanly and uses a bounded termination fallback for
a stuck child.

No browser, account, OpenAI API key, or separately installed Python is needed by the packaged app.

## Development

Source development is separate from the offline installation:

```powershell
.\scripts\setup_dev.ps1
npm start
```

Checks and packages:

```powershell
npm test
npm run pack
npm run dist
```

`npm run pack` creates an unpacked desktop build. `npm run dist` assembles the complete offline
installer and writes publishable chunks under `release\publish\v0.3.0`.

Model downloads are fixed by `scripts\download_models.ps1`:

```powershell
.\scripts\download_models.ps1 -Model david
.\scripts\download_models.ps1 -Model egirl
.\scripts\download_models.ps1 -Model qwen-fast
.\scripts\download_models.ps1 -Model qwen-best
.\scripts\download_models.ps1 -All
```

The repository excludes virtual environments, `node_modules`, model payloads, runtime builds, logs,
generated audio, and releases.

## Publication status

The source repository is public. The third-party offline payload still has a separate redistribution
gate covering recordings, model weights, RVC assets, FFmpeg, and the packaged dependency inventory.
A working local installation does not grant permission to publish those files.

The current evidence and remaining work are recorded in
[the publication audit](docs/publication-audit.md).

## Troubleshooting

- **Incomplete runtime:** reinstall with the matching EXE and sidecar in one folder.
- **CUDA unavailable:** update the NVIDIA driver and confirm the machine has a compatible NVIDIA GPU.
- **Generation failed:** inspect `%APPDATA%\Luna\logs\desktop-backend.log`.
- **Model stayed loaded:** use **Unload model**, then close Luna if the worker remains.
- **Audio will not play:** confirm the selected output folder and WAV file still exist.

## Documentation

- [Product identity, registry names, shortcuts, and user data](docs/identity-and-data.md)
- [Payload assembly and release process](docs/releasing.md)
- [Source and redistribution audit](docs/publication-audit.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Model sources

- [David Attenborough XTTS fine-tune](https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune)
- [E-Girl RVC V2](https://voice-models.com/model/1uZvOaYhqJv)
- [Qwen 0.6B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)
- [Qwen 1.7B](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)
