[CmdletBinding()]
param(
  [string]$BuildDirectory = '',
  [string]$InstrumentaRoot = '',
  [string]$NotesFile = '',
  [string]$MinimumInstrumentaVersion = '0.10.0'
)
# Builds the Luna release assets Instrumenta installs, from a copy of this checkout on a Windows
# drive, and writes instrumenta-release.json with Instrumenta's own writer and validator. It never
# publishes. The output is release\publish\v<version>; existing assets are never overwritten.
#
# 0.10.0 is the oldest launcher that accepts a payload whose single chunk carries the payload's own
# name (it reuses a verified file already at the assembled path); 0.8.0 refused to replace it.
$ErrorActionPreference = 'Stop'
$SourceRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Version = (Get-Content -LiteralPath (Join-Path $SourceRoot 'package.json') -Raw | ConvertFrom-Json).version
if (-not $BuildDirectory) { $BuildDirectory = Join-Path $env:LOCALAPPDATA "Luna\package-workspace\$Version" }
if (-not $InstrumentaRoot) { $InstrumentaRoot = Join-Path (Split-Path -Parent $SourceRoot) 'Instrumenta' }
$BuildRoot = [IO.Path]::GetFullPath($BuildDirectory)
if ($BuildRoot.StartsWith('\\') -or $BuildRoot -eq $SourceRoot -or (Test-Path -LiteralPath (Join-Path $BuildRoot '.git'))) {
  throw 'Choose an isolated build directory on a Windows drive, outside the source checkout.'
}
$ManifestWriter = Join-Path $InstrumentaRoot 'scripts\instrumenta-release.cjs'
if (-not (Test-Path -LiteralPath $ManifestWriter)) { throw "Instrumenta release writer is missing: $ManifestWriter" }
$PublishRoot = Join-Path $SourceRoot "release\publish\v$Version"
if (Test-Path -LiteralPath $PublishRoot) { throw "Refusing to overwrite existing release assets: $PublishRoot" }

New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
$Boundary = $BuildRoot.TrimEnd('\') + '\'
foreach ($Item in @('app','electron','packaging','scripts','tests','tests-electron','docs','instrumenta')) {
  $Target = [IO.Path]::GetFullPath((Join-Path $BuildRoot $Item))
  if (-not $Target.StartsWith($Boundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Build cleanup escaped the staging directory.' }
  if (Test-Path -LiteralPath $Target) { Remove-Item -LiteralPath $Target -Recurse -Force }
  Copy-Item -LiteralPath (Join-Path $SourceRoot $Item) -Destination $Target -Recurse
}
foreach ($Item in @('package.json','package-lock.json','electron-builder.config.cjs','run.py','pyproject.toml','LICENSE','THIRD_PARTY_NOTICES.md','README.md','.gitignore')) {
  Copy-Item -LiteralPath (Join-Path $SourceRoot $Item) -Destination $BuildRoot -Force
}
Get-ChildItem -LiteralPath $BuildRoot -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
$Assets = Join-Path $BuildRoot 'assets'
New-Item -ItemType Directory -Path $Assets -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceRoot 'assets\luna-icon.ico'),(Join-Path $SourceRoot 'assets\luna-icon.png') -Destination $Assets -Force
$Release = Join-Path $BuildRoot 'release'
if (Test-Path -LiteralPath $Release) { Remove-Item -LiteralPath $Release -Recurse -Force }
Push-Location $BuildRoot
try {
  & npm.cmd ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Windows build dependency installation failed.' }
  & (Join-Path $BuildRoot 'scripts\build_installer.ps1') -SkipReleaseSplit
  if ($LASTEXITCODE -ne 0) { throw 'Luna packaging failed.' }
} finally { Pop-Location }
$Installers = @(Get-ChildItem -LiteralPath $Release -Recurse -File -Filter "Luna-Installer-$Version.exe")
$Payloads = @(Get-ChildItem -LiteralPath $Release -Recurse -File -Filter "luna-$Version-x64.nsis.7z")
if ($Installers.Count -ne 1 -or $Payloads.Count -ne 1) { throw 'Expected one installer and one matching NSIS payload.' }
$Payload = $Payloads[0].FullName
& (Join-Path $SourceRoot 'scripts\split_release_assets.ps1') -InputPath $Payload -InstallerPath $Installers[0].FullName -OutputDirectory $PublishRoot
$Before = Get-Content -LiteralPath (Join-Path $PublishRoot 'instrumenta-release.json') -Raw | ConvertFrom-Json
$Arguments = @($ManifestWriter, '--product', 'luna', '--version', $Version, '--strategy', 'installed-desktop', '--minimum', $MinimumInstrumentaVersion, '--installer', (Join-Path $PublishRoot "Luna-Installer-$Version.exe"), '--payload-asset', "luna-$Version-x64.nsis.7z")
foreach ($Chunk in $Before.payload.chunks) { $Arguments += @('--chunk', (Join-Path $PublishRoot $Chunk.asset)) }
if ($NotesFile) { $Arguments += @('--notes-file', $NotesFile) }
$Arguments += @('--out', (Join-Path $PublishRoot 'instrumenta-release.json'))
& node.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Instrumenta rejected the release manifest.' }
$After = Get-Content -LiteralPath (Join-Path $PublishRoot 'instrumenta-release.json') -Raw | ConvertFrom-Json
if ($After.payload.sha256 -ne $Before.payload.sha256 -or $After.payload.size -ne $Before.payload.size) { throw 'Assembled release hashes do not match the original sidecar.' }
if ($After.payload.sha256 -ne (Get-FileHash -Algorithm SHA256 -LiteralPath $Payload).Hash.ToLowerInvariant()) { throw 'The published payload is not the built one.' }
Copy-Item -LiteralPath (Join-Path $SourceRoot 'LICENSE'),(Join-Path $SourceRoot 'THIRD_PARTY_NOTICES.md') -Destination $PublishRoot
$Sums = Get-ChildItem -LiteralPath $PublishRoot -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name | ForEach-Object {
  "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant(), $_.Name
}
[IO.File]::WriteAllText((Join-Path $PublishRoot 'SHA256SUMS.txt'), (($Sums -join "`n") + "`n"), [Text.UTF8Encoding]::new($false))
Write-Host "Luna $Version Instrumenta assets: $PublishRoot"
Write-Host "Packaged app for testing: $Release\win-unpacked\Luna.exe"
