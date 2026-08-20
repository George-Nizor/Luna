$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot
if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Missing .venv. Run scripts\setup_dev.ps1 first." }

$testTemp = Join-Path $ProjectRoot ".pytest-tmp"
New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
try {
  & ".venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider --basetemp (Join-Path $testTemp "current")
  if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE." }
  & ".venv\Scripts\python.exe" -m ruff check --no-cache app tests
  if ($LASTEXITCODE -ne 0) { throw "Ruff failed with exit code $LASTEXITCODE." }
  & node --check app\static\app.js
  if ($LASTEXITCODE -ne 0) { throw "app.js syntax check failed with exit code $LASTEXITCODE." }
  & node --check electron\main.cjs
  if ($LASTEXITCODE -ne 0) { throw "Electron main-process syntax check failed with exit code $LASTEXITCODE." }
  & node --check electron\preload.cjs
  if ($LASTEXITCODE -ne 0) { throw "Electron preload syntax check failed with exit code $LASTEXITCODE." }
} finally {
  if (Test-Path -LiteralPath $testTemp) { Remove-Item -LiteralPath $testTemp -Recurse -Force }
}
