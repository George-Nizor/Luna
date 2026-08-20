$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Error "Missing .venv. Run setup_dev.ps1 first."; exit 1 }
& $python -c "import sys; print('Python:', sys.version)"
& $python -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('CUDA runtime:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning "PyTorch is not importable. Install a CUDA-enabled build for real Qwen inference." }
& $python -c "import qwen_tts; print('qwen_tts: import ok')" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Warning "qwen_tts is not importable." }
$coquiPackage = Join-Path $ProjectRoot ".venv\Lib\site-packages\TTS"
if (Test-Path $coquiPackage) { Write-Host "coqui XTTS: package present (verified by the David worker on generation)" } else { Write-Warning "Coqui XTTS package is missing; David Attenborough generation will be unavailable." }
$egirlDirectory = Join-Path $ProjectRoot "data\models\rvc\egirl"
if (-not (Test-Path (Join-Path $egirlDirectory "egirl.pth"))) { Write-Warning "E-Girl RVC checkpoint is missing. Run download_models.ps1 -Model egirl." }
if (-not (Get-ChildItem -LiteralPath $egirlDirectory -Filter "*.index" -File -ErrorAction SilentlyContinue)) { Write-Warning "E-Girl RVC index is missing. Run download_models.ps1 -Model egirl." }
$rvcBaseDirectory = Join-Path $ProjectRoot ".venv\Lib\site-packages\rvc_python\base_model"
if (-not (Test-Path (Join-Path $rvcBaseDirectory "hubert_base.pt"))) { Write-Warning "E-Girl RVC runtime asset hubert_base.pt is missing. The app will not download it automatically because it is outside the fixed model registry." }
Write-Host "rvc-python/Fairseq: checked when the isolated E-Girl worker starts"
& $python -c "import soundfile; print('soundfile: import ok')"
if ($LASTEXITCODE -ne 0) { Write-Error "soundfile is not importable."; exit 1 }
foreach ($dir in @("data", "data\profiles", "data\outputs", "data\temp", "data\model_cache", "data\model_cache\downloads", "data\models", "runtime", "logs")) { $path = Join-Path $ProjectRoot $dir; New-Item -ItemType Directory -Force $path | Out-Null; $test = Join-Path $path ".doctor-write-test"; [IO.File]::WriteAllText($test, "ok"); Remove-Item $test -Force; Write-Host "Writable: $dir" }
$drive = Get-PSDrive -Name ((Get-Item $ProjectRoot).PSDrive.Name); Write-Host "Free disk (bytes):" $drive.Free
$portInUse = Get-NetTCPConnection -LocalPort 7865 -State Listen -ErrorAction SilentlyContinue; if ($portInUse) { Write-Warning "Port 7865 is already in use." } else { Write-Host "Port 7865: available" }
