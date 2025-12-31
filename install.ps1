param(
    [string]$VenvPath = ".venv"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment at $VenvPath..."
    python -m venv $VenvPath
}

$python = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python executable not found in $VenvPath. venv creation may have failed."
}

Write-Host "Upgrading pip..."
& $python -m pip install --upgrade pip

Write-Host "Installing requirements..."
& $python -m pip install -r requirements.txt

Write-Host "Done. Activate with:`n  $VenvPath\Scripts\Activate.ps1"
