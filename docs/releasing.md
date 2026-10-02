# Luna release and payload assembly

## Source-only repository

The public repository contains application source, tests, packaging scripts, manifests, notices,
and documentation. It excludes `.venv`, `node_modules`, model and voice payloads, Hugging Face caches,
logs, generated audio, temporary flattened snapshots, build directories, installers, and release
artifacts. Reference audio is publishable only when its ownership and redistribution permission are
recorded; otherwise it remains ignored and is supplied through the private release-assembly input.

Before publication, run secret, generated-file, dependency-license, and asset-redistribution audits.
Preserve third-party notices and do not apply the MIT license to third-party models or recordings.

## Build

From Windows PowerShell:

```powershell
npm ci
npm test
npm run dist
```

The default build includes the application and Python/CUDA runtime, with optional voice weights acquired inside Luna. Use `-IncludeModels` for an explicit offline model bundle. It creates the NSIS installer and sidecar payload, then invokes
`scripts/split_release_assets.ps1`. The splitter writes uploadable assets to
`release\publish\v0.4.1` without modifying source inputs.

### Local-only rebuild from an installed payload

An owner may rebuild Luna locally from a previously installed, complete Luna payload while replacing
the application and backend code with the current source checkout:

```powershell
.\scripts\build_installer.ps1 `
  -InstalledPayloadRoot "$env:LOCALAPPDATA\Programs\Luna\resources" `
  -SkipReleaseSplit `
  -IncludeModels
```

This recovery path copies the installed portable Python runtime, models, and voice assets into a new
local installer. It bypasses public release splitting intentionally and **must not be used for a
public release**. Do not upload, redistribute, or retain its sidecar beyond the local installation
unless every included third-party model and recording has been cleared for redistribution.

## Instrumenta packaging from this suite

`npm run package:instrumenta` mirrors the current source onto a Windows drive, reuses the locally
installed Python runtime, builds without bundled voices, splits the payload, and runs Instrumenta's
shared `scripts/instrumenta-release.cjs` writer/validator over the real assets. It does not publish.
Pass `-BuildDirectory` and `-InstalledPayloadRoot` to `scripts/package_instrumenta.ps1` to override
its local staging/runtime paths. Its output is `release/publish/v<package version>`; existing release
assets are never overwritten. Keep the native staging folder while testing its `win-unpacked` app. Set
`LUNA_USER_DATA_DIRECTORY` to an absolute test folder for an isolated packaged run; Windows
Electron resolves AppData through the shell and does not use an `APPDATA` override for this path.
For publication, first assemble a new runtime with `scripts/prepare_public_runtime.py`
using the reviewed package plan, verified wheel overlays and supplemental notices.
Preserve its source archive and licence inventory. Pass `-PublicRelease` and that
runtime's parent as `-InstalledPayloadRoot`; the public gate verifies package pins,
licence files and every recorded SHA-256 before building. An unreviewed installed
runtime is suitable only for a local recovery build. See `publication-audit.md`.

An upgrade preserves old bundled model files in `%APPDATA%\luna\data\legacy` before the old
uninstaller runs. Every copied file is checked by size and SHA-256; a conflict or copy failure stops
installation before removal. David, E-Girl and bundled Qwen Base checkpoints then load from that
persistent location. New installations acquire the optional official packs through the voice library.

## Multipart contract

GitHub release assets must remain below 2 GiB. Luna uses 1.9 GiB maximum numbered parts:

```text
luna-0.4.1-x64.nsis.7z.part001
luna-0.4.1-x64.nsis.7z.part002
...
```

`instrumenta-release.json` records the installer, assembled payload, ordered chunks, exact byte
sizes, and lowercase SHA-256 digests. Instrumenta downloads each chunk to a partial file, resumes
with HTTP Range when supported, retries only the failed chunk, checks available disk space, verifies
every chunk, assembles into a new temporary file, verifies the complete payload, then invokes the
installer. Corrupt or incomplete assets are never executed. Failed staging content is safe to clean
up because the installed application and source tree are separate.

## Release checklist

1. Confirm package, Python, Electron, installer, product manifest, and documentation versions are
   all 0.4.1.
2. Run the identity audit and complete backend/UI tests.
3. Build on Windows x64 and test insufficient-space, resume, retry, and corrupt-chunk behavior.
4. Reconstruct the payload from the publish directory and compare its SHA-256 to the source sidecar.
5. Install on a clean account, generate and play audio, uninstall, and confirm the old identity is
   absent.
6. Attach the installer, every numbered part, `instrumenta-release.json`, license, and third-party
   notices to the GitHub Release.
7. Download the public assets into a new directory and verify all hashes again before marking the
   release stable.

GitHub Releases are canonical. A sibling source checkout is a manual developer override and never a
replacement for the release artifacts.