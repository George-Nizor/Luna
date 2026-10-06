[CmdletBinding()]
param(
  [switch]$UnpackedOnly,
  [switch]$SkipReleaseSplit
)

# Builds Luna for Windows x64: the Electron app, the backend source and the runtime plan
# (packaging/runtime: runtime-lock.json, the three bundled wheels, the patch and check scripts)
# with a pinned uv.exe. There is no Python runtime and there are no voice models in the package:
# Luna installs the runtime on first start (electron/runtime-setup.cjs) and voices from its library.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Version = (Get-Content -LiteralPath (Join-Path $ProjectRoot "package.json") -Raw | ConvertFrom-Json).version
Set-Location $ProjectRoot

# uv, pinned by version and SHA-256 (https://github.com/astral-sh/uv/releases).
$UvVersion = "0.12.23"
$UvArchiveSha256 = "75d05de6762778c31ee183398de7dd15093fad0ed90b1f236d8205ea5ec00c90"
$UvLicenses = @{
  "LICENSE-MIT" = "860e3d7a86b84e6a7012c7a635fc64df475cebc6cce34dfeb73a5982ec58176c"
  "LICENSE-APACHE" = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"
}

function Get-Sha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

$lock = Get-Content -LiteralPath (Join-Path $ProjectRoot "packaging\runtime\runtime-lock.json") -Raw | ConvertFrom-Json
if ($lock.uv -ne $UvVersion) { throw "runtime-lock.json expects uv $($lock.uv); this script bundles $UvVersion." }
foreach ($package in @($lock.packages | Where-Object { $_.bundled })) {
  $wheel = Join-Path $ProjectRoot ("packaging\runtime\" + $package.bundled.Replace('/', '\'))
  if (-not (Test-Path -LiteralPath $wheel) -or (Get-Sha256 $wheel) -ne $package.sha256) { throw "Bundled wheel is missing or differs from the lock: $wheel" }
}

$uvRoot = Join-Path $ProjectRoot "build\uv-$UvVersion"
if (-not (Test-Path -LiteralPath (Join-Path $uvRoot "uv.exe"))) {
  $download = Join-Path $ProjectRoot "build\uv-$UvVersion.zip"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $download) | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $download
  if ((Get-Sha256 $download) -ne $UvArchiveSha256) { Remove-Item -LiteralPath $download -Force; throw "uv $UvVersion archive failed its SHA-256 check." }
  $staging = "$uvRoot.partial"
  if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
  Expand-Archive -LiteralPath $download -DestinationPath $staging
  foreach ($name in $UvLicenses.Keys) {
    $target = Join-Path $staging $name
    Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/astral-sh/uv/$UvVersion/$name" -OutFile $target
    if ((Get-Sha256 $target) -ne $UvLicenses[$name]) { throw "uv $name failed its SHA-256 check." }
  }
  Remove-Item -LiteralPath (Join-Path $staging "uvx.exe"),(Join-Path $staging "uvw.exe") -ErrorAction SilentlyContinue
  Move-Item -LiteralPath $staging -Destination $uvRoot
  Remove-Item -LiteralPath $download -Force
}

$env:LUNA_UV_DIRECTORY = $uvRoot
# Run electron-builder's CLI with node directly: the .cmd shim depends on cmd.exe resolving
# "node" from PATH, which some shells (WSL interop among them) do not provide.
$builder = Join-Path $ProjectRoot "node_modules\electron-builder\cli.js"
try {
  if ($UnpackedOnly) {
    & node.exe $builder --win dir --x64 --publish never --config electron-builder.config.cjs
  } else {
    & node.exe $builder --win nsis-web --x64 --publish never --config electron-builder.config.cjs
  }
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE." }
  if (-not $UnpackedOnly -and -not $SkipReleaseSplit) {
    $installer = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "release") -Recurse -File -Filter "Luna-Installer-$Version.exe" | Where-Object { $_.FullName -notlike "*\publish\*" })
    $sidecar = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "release") -Recurse -File -Filter "luna-$Version-x64.nsis.7z" | Where-Object { $_.FullName -notlike "*\publish\*" })
    if ($installer.Count -ne 1 -or $sidecar.Count -ne 1) {
      throw "Expected one Luna $Version installer and one matching NSIS sidecar before release splitting."
    }
    & (Join-Path $PSScriptRoot "split_release_assets.ps1") -InputPath $sidecar[0].FullName -InstallerPath $installer[0].FullName
    if ($LASTEXITCODE -ne 0) { throw "Release asset preparation failed with exit code $LASTEXITCODE." }
  }
} finally {
  Remove-Item Env:LUNA_UV_DIRECTORY -ErrorAction SilentlyContinue
}
