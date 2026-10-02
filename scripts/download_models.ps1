param(
  [ValidateSet("david", "egirl", "qwen-fast", "qwen-best", "qwen-voices-fast", "qwen-voices-high", "qwen-clone-fast", "qwen-clone-high")]
  [string]$Model,
  [switch]$All
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Missing .venv. Run .\scripts\setup_dev.ps1 first." }
$downloadDirectory = Join-Path $ProjectRoot "data\model_cache\downloads"
$modelsDirectory = Join-Path $ProjectRoot "data\models"
New-Item -ItemType Directory -Force $downloadDirectory, $modelsDirectory | Out-Null

function Download-Archive([string]$Url, [string]$Target) {
  Write-Host "Downloading $Target (resumable with curl)..."
  & curl.exe -L --fail --retry 3 --retry-delay 2 -C - -o $Target $Url
  if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
}

function Install-David {
  $target = Join-Path $downloadDirectory "david_attenborough_xtts.zip"
  $url = "https://huggingface.co/drewThomasson/xtts_David_Attenborough_fine_tune/resolve/main/Finished_model_files.zip?download=true"
  Download-Archive $url $target
  $expected = "1cee904839ee964d52accb6ac4639c639fda3c5db10c386742e877f6259baabe"
  $actual = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -ne $expected) { throw "David XTTS checksum mismatch. Expected $expected but received $actual." }
  $destination = Join-Path $modelsDirectory "xtts\david_attenborough"
  New-Item -ItemType Directory -Force $destination | Out-Null
  Expand-Archive -LiteralPath $target -DestinationPath $destination -Force
  $datasetArchive = Get-ChildItem $destination -Recurse -Filter "dataset.zip" -File | Select-Object -First 1
  if ($datasetArchive -and -not (Test-Path (Join-Path (Split-Path $datasetArchive.FullName) "ref.wav"))) {
    $datasetTemp = Join-Path $ProjectRoot "data\temp\david_dataset_extract"
    New-Item -ItemType Directory -Force $datasetTemp | Out-Null
    Expand-Archive -LiteralPath $datasetArchive.FullName -DestinationPath $datasetTemp -Force
    $reference = Get-ChildItem $datasetTemp -Recurse -Filter "*.wav" -File | Select-Object -First 1
    if ($reference) { Copy-Item -LiteralPath $reference.FullName -Destination (Join-Path (Split-Path $datasetArchive.FullName) "ref.wav") -Force }
    Remove-Item -LiteralPath $datasetTemp -Recurse -Force
  }
  Write-Host "David XTTS extracted to $destination"
}

function Install-Egirl {
  $target = Join-Path $downloadDirectory "egirl_rvc.zip"
  $url = "https://huggingface.co/pendmg/Models/resolve/main/egirl.zip?download=true"
  Download-Archive $url $target
  $destination = Join-Path $modelsDirectory "rvc\egirl"
  New-Item -ItemType Directory -Force $destination | Out-Null
  Expand-Archive -LiteralPath $target -DestinationPath $destination -Force
  $sourceReference = Join-Path $ProjectRoot "assets\egirl-source-reference.wav"
  if (-not (Test-Path -LiteralPath $sourceReference)) { throw "Missing fixed E-Girl source reference: $sourceReference" }
  Copy-Item -LiteralPath $sourceReference -Destination (Join-Path $destination "source_ref.wav") -Force
  Write-Host "E-Girl RVC extracted to $destination"
}

function Install-Qwen([string]$Pack) {
  & ".venv\Scripts\python.exe" scripts\acquire_voice_packs.py $Pack
  if ($LASTEXITCODE -ne 0) { throw "Qwen download failed: $Pack" }
  Write-Host "$Pack verified and installed in data\model-packs."
}

if ($All -or $Model -eq "david") { Install-David }
if ($All -or $Model -eq "egirl") { Install-Egirl }
if ($All -or $Model -in @("qwen-fast", "qwen-clone-fast")) { Install-Qwen "qwen-clone-fast" }
if ($All -or $Model -in @("qwen-best", "qwen-clone-high")) { Install-Qwen "qwen-clone-high" }
if ($All -or $Model -eq "qwen-voices-fast") { Install-Qwen "qwen-voices-fast" }
if ($All -or $Model -eq "qwen-voices-high") { Install-Qwen "qwen-voices-high" }
if (-not $All -and -not $Model) { throw "Choose -Model david|egirl|qwen-fast|qwen-best or use -All." }
