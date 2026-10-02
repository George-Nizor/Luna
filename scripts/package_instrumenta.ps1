[CmdletBinding()]
param(
  [string]$InstalledPayloadRoot = (Join-Path $env:LOCALAPPDATA 'Programs\Luna\resources'),
  [string]$BuildDirectory = '',
  [string]$InstrumentaRoot = '',
  [switch]$PublicRelease
)
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
if (-not (Test-Path -LiteralPath (Join-Path $InstalledPayloadRoot 'python\python.exe'))) { throw 'The installed Luna Python runtime is required for this local packaging command.' }
if ($PublicRelease) {
  & (Join-Path $InstalledPayloadRoot 'python\python.exe') -I (Join-Path $SourceRoot 'scripts\verify_public_runtime.py') (Join-Path $InstalledPayloadRoot 'python')
  if ($LASTEXITCODE -ne 0) { throw 'Public runtime review/integrity check failed.' }
}
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
$Assets = Join-Path $BuildRoot 'assets'
New-Item -ItemType Directory -Path $Assets -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $SourceRoot 'assets\luna-icon.ico'),(Join-Path $SourceRoot 'assets\luna-icon.png') -Destination $Assets -Force
Push-Location $BuildRoot
try {
  & npm.cmd ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Windows build dependency installation failed.' }
  & (Join-Path $BuildRoot 'scripts\build_installer.ps1') -InstalledPayloadRoot $InstalledPayloadRoot -SkipReleaseSplit
  if ($LASTEXITCODE -ne 0) { throw 'Luna packaging failed.' }
} finally { Pop-Location }
$Installers = @(Get-ChildItem -LiteralPath (Join-Path $BuildRoot 'release') -Recurse -File -Filter "Luna-Installer-$Version.exe")
$Payloads = @(Get-ChildItem -LiteralPath (Join-Path $BuildRoot 'release') -Recurse -File -Filter "luna-$Version-x64.nsis.7z")
if ($Installers.Count -ne 1 -or $Payloads.Count -ne 1) { throw 'Expected one installer and one matching NSIS payload.' }
$Installer = $Installers[0].FullName
$Payload = $Payloads[0].FullName
& (Join-Path $SourceRoot 'scripts\split_release_assets.ps1') -InputPath $Payload -InstallerPath $Installer -OutputDirectory $PublishRoot
$Before = Get-Content -LiteralPath (Join-Path $PublishRoot 'instrumenta-release.json') -Raw | ConvertFrom-Json
$Arguments = @($ManifestWriter, '--product', 'luna', '--version', $Version, '--strategy', 'installed-desktop', '--minimum', '0.8.0', '--installer', (Join-Path $PublishRoot "Luna-Installer-$Version.exe"), '--payload-asset', "luna-$Version-x64.nsis.7z")
foreach ($Chunk in $Before.payload.chunks) { $Arguments += @('--chunk', (Join-Path $PublishRoot $Chunk.asset)) }
$Arguments += @('--out', (Join-Path $PublishRoot 'instrumenta-release.json'))
& node.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw 'Instrumenta rejected the release manifest.' }
$After = Get-Content -LiteralPath (Join-Path $PublishRoot 'instrumenta-release.json') -Raw | ConvertFrom-Json
if ($After.payload.sha256 -ne $Before.payload.sha256 -or $After.payload.size -ne $Before.payload.size) { throw 'Assembled release hashes do not match the original sidecar.' }
Copy-Item -LiteralPath (Join-Path $SourceRoot 'LICENSE'),(Join-Path $SourceRoot 'THIRD_PARTY_NOTICES.md') -Destination $PublishRoot
Write-Host "Luna $Version Instrumenta assets: $PublishRoot"
Write-Host "Packaged runtime for testing: $BuildRoot\release\win-unpacked\Luna.exe"
