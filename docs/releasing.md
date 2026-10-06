# Luna release and runtime assembly

## Source-only repository

The public repository contains application source, tests, packaging scripts, manifests, notices,
and documentation. It excludes `.venv`, `node_modules`, model and voice payloads, Hugging Face caches,
logs, generated audio, build directories, installers, and release artifacts. Reference audio is
publishable only when its ownership and redistribution permission are recorded; otherwise it remains
ignored.

Three pure-Python wheels are committed on purpose, in `packaging/runtime/wheels` (see below).

## What a release contains

Since 0.6.0 the installer carries no Python runtime. A release is:

- `Luna-Installer-<version>.exe`, the NSIS web installer (under 1 MB);
- `luna-<version>-x64.nsis.7z`, the app package (about 110 MB): Electron, the backend source, the
  runtime lock, three bundled wheels, `apply_patches.py`, `verify_runtime.py` and `uv.exe`;
- `instrumenta-release.json`, `SHA256SUMS.txt`, `LICENSE` and `THIRD_PARTY_NOTICES.md`;
- `Electron-media-sources.zip`, the LGPL source supplement for Electron's `ffmpeg.dll`. It depends
  only on the Electron version; rebuild it (its `source-provenance.json` lists every URL and hash)
  when Electron changes.

Run alone, the installer uses the package beside it or downloads it from the same release
(`nsisWeb.appPackageUrl`). Instrumenta downloads both, verifies them and runs the installer.

## The runtime Luna installs for itself

`packaging/runtime` is a dependency-only uv project. `pyproject.toml` pins every package (the versions
the 0.4.1 runtime was reviewed and validated with), takes PyTorch 2.11.0+cu128 from PyTorch's own index,
overrides four upstream pins that cannot be met on Python 3.12 and excludes declared dependencies Luna
never imports. `uv.lock` is the resolution, with a SHA-256 for every file.

`scripts/runtime_lock.py` turns the lock into `runtime-lock.json`: for CPython 3.12 on Windows x64 it
picks one wheel per package (96 of them, 3.02 GB) with URL, size and SHA-256, and derives the lock
hash that names the environment. Electron reads only that file.

On first start, and whenever the lock hash changes, `electron/runtime-setup.cjs`:

1. installs the pinned CPython with `uv python install` into `%LOCALAPPDATA%\Luna\runtime\python`;
2. downloads every wheel into `runtime\downloads` itself, resuming with HTTP Range and checking size
   and SHA-256, so the setup screen can show real progress and continue after a restart;
3. creates `runtime\<lock hash>.partial` with `uv venv` and installs with
   `uv pip sync --require-hashes --offline --no-index --no-build` from those files and the bundled
   wheels, so uv checks every hash again and can neither resolve nor fetch anything else;
4. applies `apply_patches.py` (the five reviewed source changes 0.4.1 carried, each pinned to the
   upstream and the patched SHA-256) and runs `verify_runtime.py`: every locked distribution at its
   version and nothing else, every engine's modules importable, and whether PyTorch reaches a GPU;
5. renames the folder to `runtime\<lock hash>`, writes its marker and replaces `current.json` in one
   rename. Only then are the previous environment, the downloaded wheels, uv's cache
   (`runtime\cache`, used only during setup) and unreferenced Pythons removed.

One environment, one CPython and no wheel archive remain afterwards (about 5 GB). The backend runs
from `runtime\<lock hash>\Scripts\python.exe`. A missing GPU is reported on the setup screen and by
generation; it does not stop setup.

Why Luna downloads the wheels instead of letting `uv sync` do it: uv shows no byte progress when it
has no terminal and restarts an interrupted file from zero. The torch wheel alone is 2.75 GB.

### Changing the runtime

```bash
# from the repository root, with uv 0.12.23 or newer
uv lock --project packaging/runtime
python scripts/runtime_lock.py          # asks PyTorch's index for the sizes uv.lock lacks
python -m pytest tests/test_runtime_lock.py
```

Commit `pyproject.toml`, `uv.lock` and `runtime-lock.json` together; the tests refuse a stale plan.
A changed set gives a new lock hash, and every installed Luna sets up the new environment once. Run
a real first-run setup on Windows and generate with each engine before releasing such a change:
`verify_runtime.py` proves imports, not speech.

fairseq 0.12.2, antlr4-python3-runtime 4.8 and sox 1.5.0 publish no wheel for Python 3.12 on Windows.
`scripts/build_runtime_wheels.py` builds each from its PyPI source archive (pinned by SHA-256) as a
pure-Python wheel; fairseq is built with its own `READTHEDOCS` switch, which leaves out its native
extensions, as in 0.4.1. The build is reproducible (`SOURCE_DATE_EPOCH`), and uv.lock pins the hashes.

`build_installer.ps1` bundles uv 0.12.23 (`uv.exe` and its licences), downloaded from uv's GitHub
release and checked against a pinned SHA-256. Keep `UV_VERSION` in `scripts/runtime_lock.py` and
the script's pin in step.

## Build

From Windows PowerShell:

```powershell
npm ci
npm test
npm run dist
```

`npm run pack` builds `release\win-unpacked` only. `npm run dist` builds the installer and package and
runs `scripts/split_release_assets.ps1`, which writes the assets to `release\publish\v<version>`
without modifying its inputs.

## Instrumenta packaging

`npm run package:instrumenta` (`scripts/package_instrumenta.ps1`) copies the checkout to a Windows
build folder (`-BuildDirectory`, default `%LOCALAPPDATA%\Luna\package-workspace\<version>`), builds
there, splits the package and runs Instrumenta's shared `scripts/instrumenta-release.cjs`
writer/validator over the real files, with `-NotesFile` for the launcher's "What's new". It then
writes `SHA256SUMS.txt`. It never publishes and never overwrites existing assets. Set
`LUNA_USER_DATA_DIRECTORY` and `LUNA_RUNTIME_ROOT` to absolute test folders to run the built
`win-unpacked\Luna.exe` without touching an installed Luna's data or runtime.

## Payload contract

A package below 1.9 GiB, Luna's since 0.6.0, is published as one asset under its own name,
`luna-<version>-x64.nsis.7z`, which is also the manifest's single chunk. Larger packages are split into
numbered `.partNNN` chunks below GitHub's 2 GiB limit. `instrumenta-release.json` records the installer,
the assembled payload and its chunks with exact sizes and lowercase SHA-256 digests.

The single-chunk form needs Instrumenta 0.10.0 or newer: from that version the launcher reuses a
verified file already at the assembled path instead of refusing to replace it. Luna's
`minimumInstrumentaVersion` is 0.10.0 accordingly.

## Upgrades

An upgrade preserves old bundled model files in `%APPDATA%\luna\data\legacy` before the old
uninstaller runs (`packaging/installer.nsh`, `preserve_legacy.py`, using the old installation's own
Python). Every copied file is checked by size and SHA-256; a conflict or copy failure stops the
installation before removal. The old uninstaller then removes the previous program folder, including
a bundled `resources\python`; `customInstall` deletes any remainder. Settings, packs, profiles and
history in `%APPDATA%\luna` are not touched. The first start of the new version sets up the runtime.

## Release checklist

1. Version 0.x.y in `package.json` and its lock, `pyproject.toml`, `app/__init__.py`,
   `instrumenta/product.json`, the release template and the README.
2. `npm test` on Windows (or pytest, ruff and `node --test tests-electron/*.test.cjs`).
3. `scripts/package_instrumenta.ps1 -NotesFile <notes>`.
4. Run the built app with isolated `LUNA_USER_DATA_DIRECTORY` and `LUNA_RUNTIME_ROOT`: real
   first-run setup, a GPU generation, a second start without downloads.
5. Tag `v<version>` with the notes as its message, publish the GitHub release with every file in the
   publish folder, then download `instrumenta-release.json` from `releases/latest` and check every
   size and SHA-256 against the published files.

GitHub Releases are canonical. A sibling source checkout is a manual developer override and never a
replacement for the release artifacts.
