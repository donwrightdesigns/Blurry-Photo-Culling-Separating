# ExifTool Installation for PRO-CULL

## Why ExifTool?
PRO-CULL uses ExifTool for robust EXIF extraction from RAW files (NEF, CR2, CR3, ARW, DNG, etc.). While Pillow works for JPG/TIFF, ExifTool is the industry standard for professional RAW workflows.

## Installation (Windows)

### Option 1: Manual Download (Recommended)
1. Visit: https://exiftool.org/
2. Download **Windows Executable (64-bit)**: `exiftool-13.45_64.zip`
   - Direct link: https://sourceforge.net/projects/exiftool/files/exiftool-13.45_64.zip/download
3. Extract the ZIP file to a permanent location (e.g., `J:\TOOLS\exiftool\` or `C:\Program Files\ExifTool\`)
4. Rename `exiftool(-k).exe` → `exiftool.exe`
5. **Critical Step**: Add that folder to your Windows PATH environment variable.

### Option 2: Add to PATH Manually (PowerShell)
Replace `J:\TOOLS\exiftool` with your actual installation folder:
```powershell
$env:PATH += ";J:\TOOLS\exiftool"
[Environment]::SetEnvironmentVariable("PATH", $env:PATH, [EnvironmentVariableTarget]::User)
```
*Restart your terminal or VS Code after running this.*

### Option 3: Chocolatey (if you have it)
```powershell
choco install exiftool -y
```

## Verify Installation
```powershell
exiftool -ver
```
Should output version number (e.g., `13.45`)

## PRO-CULL Integration
PRO-CULL automatically detects ExifTool at startup:
- If found: Uses ExifTool for RAW files, Pillow for JPG/TIFF (fastest)
- If not found: Falls back to Pillow only (RAW EXIF extraction disabled)

The PRESCAN feature requires ExifTool for accurate RAW metadata extraction.

## Troubleshooting
- **Error: "exiftool not recognized"** → Add to PATH
- **PRESCAN shows empty camera models** → ExifTool not detected
- **RAW files skipped** → Install ExifTool

For help: https://exiftool.org/install.html
