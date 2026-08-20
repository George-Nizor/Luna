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

The build creates the lightweight NSIS installer, its large sidecar payload, and then invokes
`scripts/split_release_assets.ps1`. The splitter writes uploadable assets to
`release\publish\v0.3.0` without modifying source inputs.

## Multipart contract

GitHub release assets must remain below 2 GiB. Luna uses 1.9 GiB maximum numbered parts:

```text
luna-0.3.0-x64.nsis.7z.part001
luna-0.3.0-x64.nsis.7z.part002
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
   all 0.3.0.
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