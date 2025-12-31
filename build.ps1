# PRO-CULL Build Script for Windows Distribution
# Usage: .\build.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== PRO-CULL Package Builder ===" -ForegroundColor Cyan

# Step 1: Ensure venv and dependencies
Write-Host "`n[1/3] Checking virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".\.venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

$PythonExe = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "ERROR: Python venv not found" -ForegroundColor Red
    exit 1
}

Write-Host "Installing/updating dependencies..." -ForegroundColor Yellow
& $PythonExe -m pip install --quiet pyinstaller numpy opencv-python pillow piexif

# Step 2: Build GUI.exe
Write-Host "`n[2/3] Building GUI.exe with PyInstaller..." -ForegroundColor Yellow
& $PythonExe -m PyInstaller --clean --windowed --onefile `
    --name=PRO-CULL-GUI `
    --hidden-import=tkinter `
    --hidden-import=cv2 `
    --hidden-import=numpy `
    --hidden-import=PIL `
    --hidden-import=blur_detection `
    --hidden-import=process `
    --hidden-import=metrics `
    --hidden-import=metrics.composition `
    --hidden-import=metrics.lighting `
    --hidden-import=metrics.noise `
    --hidden-import=metrics.metadata `
    --hidden-import=exif_reader `
    gui.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: PyInstaller build failed" -ForegroundColor Red
    exit 1
}

# Create dist folder if it doesn't exist
if (-not (Test-Path ".\dist")) {
    mkdir ".\dist" | Out-Null
}

# Move executable to dist
$GuiExe = ".\dist\PRO-CULL-GUI.exe"
if (Test-Path ".\dist\gui.exe") {
    Move-Item ".\dist\gui.exe" $GuiExe -Force
}

if (-not (Test-Path $GuiExe)) {
    Write-Host "ERROR: GUI.exe not found in dist folder" -ForegroundColor Red
    exit 1
}

Write-Host "✓ GUI.exe created: $GuiExe" -ForegroundColor Green

# Step 3: Package for distribution
Write-Host "`n[3/3] Preparing distribution package..." -ForegroundColor Yellow

$DistRoot = ".\dist\PRO-CULL-v1-Windows"
if (Test-Path $DistRoot) {
    Remove-Item $DistRoot -Recurse -Force
}
mkdir $DistRoot | Out-Null

# Copy key files
Copy-Item $GuiExe "$DistRoot\PRO-CULL-GUI.exe"
Copy-Item ".\PRO-CULL-v1.lrplugin" "$DistRoot\PRO-CULL-v1.lrplugin" -Recurse
Copy-Item ".\install.ps1" "$DistRoot\install.ps1"
Copy-Item ".\README.md" "$DistRoot\README.md"

# Create batch launcher
$BatchContent = @'
@echo off
REM PRO-CULL Launcher
REM This script sets up the environment and launches the GUI

setlocal enabledelayedexpansion

echo.
echo ===========================
echo   PRO-CULL v1 Installer
echo ===========================
echo.

REM Check if PowerShell is available
powershell -NoProfile -ExecutionPolicy Bypass -Command "exit"
if errorlevel 1 (
    echo ERROR: PowerShell required but not available
    pause
    exit /b 1
)

REM Run installation script
powershell -NoProfile -ExecutionPolicy Bypass -File "install.ps1"
if errorlevel 1 (
    echo.
    echo Installation failed!
    pause
    exit /b 1
)

echo.
echo Installation complete! Launching GUI...
echo.

REM Launch GUI
start "" "PRO-CULL-GUI.exe"
exit /b 0
'@

$BatchContent | Out-File "$DistRoot\START.bat" -Encoding ASCII

# Create README for distribution
$DistReadme = @'
PRO-CULL v1 - Windows Distribution

QUICK START:

1. Double-click START.bat
   This will:
   - Set up Python environment
   - Install all required dependencies
   - Launch the GUI

2. Use the GUI to analyze your photo folders

3. Use the Lightroom Plugin
   - Copy PRO-CULL-v1.lrplugin folder into Lightroom plugins directory
   - Or use File > Plug-in Manager > Add

REQUIREMENTS:

- Windows 10+ (64-bit)
- Lightroom Classic (optional, for plugin features)
- 1 GB disk space

FIRST TIME SETUP:

- START.bat handles everything automatically
- Network access required for initial dependency download (500MB)

FILES INCLUDED:

- PRO-CULL-GUI.exe - Standalone GUI tool (no installation needed)
- PRO-CULL-v1.lrplugin - Lightroom Classic plugin
- install.ps1 - Dependency setup script
- README.md - Full documentation

SUPPORT:

For issues or questions, contact the development team.
'@

$DistReadme | Out-File "$DistRoot\QUICKSTART.txt" -Encoding UTF8

Write-Host "✓ Distribution package ready: $DistRoot" -ForegroundColor Green

# Summary
Write-Host "`n=== Build Complete ===" -ForegroundColor Green
Write-Host "Distribution folder: $DistRoot" -ForegroundColor Cyan
Write-Host "GUI executable: $GuiExe" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Share the '$DistRoot' folder with testers" -ForegroundColor White
Write-Host "2. Testers double-click START.bat to set up" -ForegroundColor White
Write-Host "3. GUI and Lightroom plugin ready to use" -ForegroundColor White
Write-Host ""
