$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# The development .venv is the same locked runtime the installed app sets up for itself
# (packaging/runtime), plus the test tools in requirements-dev.txt.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Install uv first: https://docs.astral.sh/uv/" }
$lock = Get-Content -LiteralPath "packaging\runtime\runtime-lock.json" -Raw | ConvertFrom-Json
$env:UV_PROJECT_ENVIRONMENT = Join-Path $ProjectRoot ".venv"
try {
  & uv python install $lock.python
  & uv sync --frozen --no-install-project --python $lock.python --project packaging\runtime
  if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }
} finally { Remove-Item Env:UV_PROJECT_ENVIRONMENT -ErrorAction SilentlyContinue }
& ".venv\Scripts\python.exe" -I packaging\runtime\apply_patches.py ".venv\Lib\site-packages"
& uv pip install --python ".venv\Scripts\python.exe" -r requirements-dev.txt
& npm install
& "$PSScriptRoot\doctor.ps1"
Write-Host "Development setup complete. Run 'npm start' or build with 'npm run dist'."
