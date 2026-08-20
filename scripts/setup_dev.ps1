$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) { $pythonCommand = "py -3.12" } else { $pythonCommand = "python" }
if (-not (Test-Path ".venv\Scripts\python.exe")) { Invoke-Expression "$pythonCommand -m venv .venv" }
& ".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
& npm install
& "$PSScriptRoot\doctor.ps1"
Write-Host "Development setup complete. Run 'npm start' or build with 'npm run dist'."
