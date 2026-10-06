![Luna banner](docs/images/luna-banner.png)

<p align="center"><img src="docs/brand/luna-animated.svg" alt="Luna crescent with a voice" width="96" /></p>

# Luna

Private, local GPU voice generation.

![Luna in the dark theme: the voice visualiser, the text composer and the voice controls](docs/images/luna-studio-dark.png)

Luna is a Windows desktop app for local GPU speech generation, launched from Instrumenta, the Start
menu, or `Luna.exe`. It opens a private backend in an Electron window. Text, reference recordings,
profiles, and generated WAV files remain on your computer.

The installer is small (about 110 MB) and holds no Python. On first start Luna sets up its own
runtime: Python 3.12 and the locked libraries it speaks with, PyTorch with CUDA 12.8 among them.
That is a 3.02 GB download, once, which takes about 5 GB under `%LOCALAPPDATA%\Luna\runtime`. The
setup screen shows the size, progress and speed; cancelling or a lost connection keeps what has
arrived, and the next start resumes. Updates to Luna reuse the runtime unless its locked dependency
set changes, in which case Luna sets up the new one and removes the old one after it works.

Current source version: **0.6.0**.

## Choose voices and models

Open **Voices** in the top bar (or **Get / manage voices** in Settings). Choose which speakers appear in your voice menu, then download the
quality packs you want. The catalog displays exact download sizes, available disk space, official
sources, installation status, and progress. Downloads can be paused and resumed. Every file is
checked against a pinned revision and checksum before the pack becomes available.

![The voice library in the light theme, with nine Qwen speakers ready and the shared packs below](docs/images/luna-voice-library-light.png)

- **Official Qwen speakers:** Ryan, Aiden, Vivian, Serena, Uncle Fu, Dylan, Eric, Ono Anna, and Sohee.
  Fast uses the 0.6B CustomVoice model; High uses the separate 1.7B CustomVoice model.
- **Shared voice packs:** Fast is approximately 2.50 GB and High approximately 4.52 GB. Each includes
  all nine speakers. Selecting one speaker does not require another copy of the shared weights.
- **Saved voice profiles:** Upload a recording you own or have permission to use, and its exact
  transcript. Separate optional Base packs provide Fast and High voice cloning.
- **David Attenborough:** Existing offline installations can retain this XTTS fine-tune. It contains
  one checkpoint, labeled **Original**. A quality switch cannot create a higher-quality checkpoint.
- **E-Girl:** Existing offline installations can retain RVC conversion. When the matching official
  voice pack is present, Luna uses its Serena speaker as the clean source. Otherwise it uses the
  existing reference-cloning source. RVC conversion can affect clarity.

High mode on official Qwen speakers supports optional style directions. Fast does not support that
control. An optional seed is saved with every generation so you can compare settings. Qwen-based voices also expose sampling temperature (0.2–1.2; default 0.7). Lower values are steadier; higher values add variation.

New installations open the voice library when no selected voice is ready. Model loading never starts
an implicit download. An NVIDIA GPU with a current driver (570 or newer, for CUDA 12.8) is required;
larger models need more GPU memory. Without one, setup still completes and says so, and generation
reports that no GPU is reachable. Use **Unload** when another application needs the GPU.

## Text limits

The text box displays and enforces the backend's character limit (5,000 by default). Model and
language determine safe segment sizes; Qwen's configured audio-token budget is also accounted for.
Qwen currently uses up to 140 characters per Fast segment and 100 per High segment, further reduced when its audio budget requires it. Long text is generated in bounded segments and joined into one WAV. A model exhausting its audio
budget returns an error rather than saving partial speech as a successful generation.

Generation has a one-hour default timeout to accommodate longer High-quality jobs. Administrators
can adjust the limits in the environment configuration.

## Generation library and exports

**Sound history** keeps every generation until you delete it. Search the text or voice, filter by quality,
and page through all results. Each entry includes playback, WAV export, metadata export, Explorer
reveal in the desktop app, and deletion.

**Reuse text** restores the original text, voice, language, quality, style, and seed to the editor.
Change any parameters, then generate a new output. This preserves the original generation.

Details record model provenance, seed, duration, generation time, sample rate, file size, character
count, and segment count. Older outputs remain readable. Versions that did not save their text cannot
supply it for reuse. Audio already deleted by an older retention policy cannot be recovered by Luna.

The default output location is `%USERPROFILE%\Documents\Luna`. Settings can change it. Previous
selected output folders remain in the library. Exporting a WAV creates a separate copy; deleting the
generation removes its managed WAV and metadata.

Settings and downloaded packs live under `%APPDATA%\Luna`; packs are in `data\model-packs`.
Backend logs are in `logs\desktop-backend.log`, runtime setup failures in `logs\runtime-setup.log`.
The Python runtime lives under `%LOCALAPPDATA%\Luna\runtime`. Uninstalling preserves your data.

## Development and packaging

```powershell
.\scripts\setup_dev.ps1
npm start
npm test
npm run pack
npm run dist
```

`scripts\setup_dev.ps1` builds `.venv` from the same lock the installed app uses
(`packaging/runtime`), with uv. Installers contain the app, the backend source, the runtime lock and a
pinned `uv.exe`; no Python, no CUDA libraries and no voice weights. How the runtime is locked, set
up and released is in [Release assembly](docs/releasing.md).

The verified developer downloader uses the same catalog:

```powershell
.\scripts\download_models.ps1 -Model qwen-voices-fast
.\scripts\download_models.ps1 -Model qwen-voices-high
.\scripts\download_models.ps1 -Model qwen-clone-fast
.\scripts\download_models.ps1 -Model qwen-clone-high
```

The old `qwen-fast` and `qwen-best` command names remain aliases for cloning packs.
Models, reference recordings, runtime payloads, logs, QA audio, and builds are excluded from Git.

## Documentation and sources

- [Model catalog and generation library](docs/voice-library.md)
- [Identity and local data](docs/identity-and-data.md)
- [Release assembly](docs/releasing.md)
- [Publication audit](docs/publication-audit.md)
- [Brand v2 in Luna](docs/brand/README.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Official Qwen Fast voices](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice)
- [Official Qwen High voices](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)
- [David XTTS source](https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune)
- [E-Girl RVC source](https://voice-models.com/model/1uZvOaYhqJv)

Source improvements do not publish or replace an installed release. Luna no longer redistributes a
Python runtime; legacy recordings and weights are still not redistributed (see the publication audit).

## Family

Luna is part of [Instrumenta](https://github.com/George-Nizor/Instrumenta), made by Bonehead Labs, and
follows the Instrumenta brand v2: a crescent moon with a voice, drawn as a freestanding object, in a
deliberately quiet lunar blue. The interface type (Fraunces, Commissioner, Spline Sans Mono) is SIL
OFL 1.1, vendored in `app/static/brand/fonts` with its licences. Licence: MIT ([LICENSE](LICENSE));
bundled components keep their own ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
See [docs/brand/README.md](docs/brand/README.md) for what was taken from the brand and what was kept.
