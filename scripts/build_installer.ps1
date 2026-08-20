[CmdletBinding()]
param([switch]$UnpackedOnly)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$venvConfig = Join-Path $ProjectRoot ".venv\pyvenv.cfg"
if (-not (Test-Path -LiteralPath $venvConfig)) { throw "Missing development environment. Run scripts\setup_dev.ps1 first." }
$homeLine = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
if (-not $homeLine) { throw "Could not locate the portable Python base from .venv\pyvenv.cfg." }
$pythonBase = ($homeLine -split '=', 2)[1].Trim()

$required = @(
  (Join-Path $pythonBase "python.exe"),
  (Join-Path $ProjectRoot ".venv\Lib\site-packages\torch"),
  (Join-Path $ProjectRoot ".venv\Lib\site-packages\qwen_tts"),
  (Join-Path $ProjectRoot "data\models\xtts\david_attenborough"),
  (Join-Path $ProjectRoot "data\models\rvc\egirl\egirl.pth"),
  (Join-Path $ProjectRoot "assets\egirl-source-reference.wav"),
  (Join-Path $ProjectRoot "assets\luna-icon.ico"),
  (Join-Path $ProjectRoot "data\model_cache\hub\models--Qwen--Qwen3-TTS-12Hz-0.6B-Base"),
  (Join-Path $ProjectRoot "data\model_cache\hub\models--Qwen--Qwen3-TTS-12Hz-1.7B-Base")
)
$missing = $required | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing) { throw "The complete installer payload is missing:`n$($missing -join "`n")" }
Copy-Item -LiteralPath (Join-Path $ProjectRoot "assets\egirl-source-reference.wav") -Destination (Join-Path $ProjectRoot "data\models\rvc\egirl\source_ref.wav") -Force

$payloadRoot = Join-Path $ProjectRoot "build\model-payload"
function Add-FlattenedQwenSnapshot([string]$RepositoryCache, [string]$TargetName) {
  $revision = (Get-Content -Raw -LiteralPath (Join-Path $RepositoryCache "refs\main")).Trim()
  $snapshot = Join-Path $RepositoryCache "snapshots\$revision"
  if (-not (Test-Path -LiteralPath (Join-Path $snapshot "config.json"))) {
    throw "Qwen snapshot is incomplete: $snapshot"
  }
  $target = Join-Path $payloadRoot $TargetName
  New-Item -ItemType Directory -Force -Path $target | Out-Null
  foreach ($item in Get-ChildItem -LiteralPath $snapshot -Recurse -File -Force) {
    $relative = $item.FullName.Substring($snapshot.Length).TrimStart('\')
    $destination = Join-Path $target $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    $source = $item.FullName
    if ($item.LinkType) {
      $linkTarget = @($item.Target)[0]
      $source = [IO.Path]::GetFullPath((Join-Path $item.DirectoryName $linkTarget))
    }
    New-Item -ItemType HardLink -Path $destination -Target $source | Out-Null
  }
}

$payloadFullPath = [IO.Path]::GetFullPath($payloadRoot)
$buildRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "build"))
if (-not $payloadFullPath.StartsWith($buildRoot, [StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to prepare a model payload outside the project build directory."
}
if (Test-Path -LiteralPath $payloadRoot) { Remove-Item -LiteralPath $payloadRoot -Recurse -Force }
Add-FlattenedQwenSnapshot (Join-Path $ProjectRoot "data\model_cache\hub\models--Qwen--Qwen3-TTS-12Hz-0.6B-Base") "qwen-fast"
Add-FlattenedQwenSnapshot (Join-Path $ProjectRoot "data\model_cache\hub\models--Qwen--Qwen3-TTS-12Hz-1.7B-Base") "qwen-best"

$env:VOICE_STUDIO_PYTHON_BASE = $pythonBase
try {
  if ($UnpackedOnly) {
    & .\node_modules\.bin\electron-builder.cmd --win dir --x64 --config electron-builder.config.cjs
  } else {
    & .\node_modules\.bin\electron-builder.cmd --win nsis-web --x64 --config electron-builder.config.cjs
  }
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE." }
  if (-not $UnpackedOnly) {
    $installer = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "release") -Recurse -File -Filter "Luna-Installer-0.3.0.exe" | Where-Object { $_.FullName -notlike "*\\publish\\*" })
    $sidecar = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "release") -Recurse -File -Filter "luna-0.3.0-x64.nsis.7z" | Where-Object { $_.FullName -notlike "*\\publish\\*" })
    if ($installer.Count -ne 1 -or $sidecar.Count -ne 1) {
      throw "Expected one Luna 0.3.0 installer and one matching NSIS sidecar before release splitting."
    }
    & (Join-Path $PSScriptRoot "split_release_assets.ps1") -InputPath $sidecar[0].FullName -InstallerPath $installer[0].FullName
    if ($LASTEXITCODE -ne 0) { throw "Release asset preparation failed with exit code $LASTEXITCODE." }
  }
} finally {
  Remove-Item Env:VOICE_STUDIO_PYTHON_BASE -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $payloadRoot) { Remove-Item -LiteralPath $payloadRoot -Recurse -Force }
}
