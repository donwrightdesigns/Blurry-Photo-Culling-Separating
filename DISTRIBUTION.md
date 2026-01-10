# PRO-CULL v1 - Windows Distribution Package

## Overview

The complete distribution package for non-technical photographers is located at:

```
dist/PRO-CULL-v1-Windows/
```

This folder contains everything needed for professional photographers to use PRO-CULL without any command-line knowledge or technical setup.

## Package Contents

### Core Files

- **START.bat** (recommended for all users)
  - One-click installer and launcher
  - Handles all setup automatically
  - First run: 3-5 minutes (downloads ~500MB)
  - Subsequent runs: ~5 seconds
  - Safe to run multiple times

- **PRO-CULL-GUI.exe** (66 MB, for advanced users)
  - Standalone GUI application
  - Fully self-contained executable
  - Windows 10+ (64-bit)
  - May require system tkinter installation

- **PRO-CULL-v1.lrplugin/** (Lightroom plugin)
  - Complete Lightroom Classic plugin
  - Integrates into Lightroom menu system
  - Settings dialog for metric configuration
  - Non-destructive XMP output

### Documentation

- **SETUP_GUIDE.txt**
  - Complete user guide for photographers
  - Metric explanations and scoring guide
  - Troubleshooting section
  - Lightroom integration instructions
  - Uninstall instructions

- **README.md**
  - Full technical documentation
  - CLI usage
  - Advanced options
  - File format specifications

- **install.ps1**
  - Automated dependency installer
  - Runs via START.bat (no user action needed)
  - Installs Python packages: numpy, opencv-python, pillow, piexif

## Distribution Instructions

### For End Users

1. **Share the entire `dist/PRO-CULL-v1-Windows/` folder** with testers
2. Users simply **double-click START.bat**
3. Everything else happens automatically

### For Publishing/Sharing

#### Option 1: ZIP Distribution
```powershell
# Create a ZIP file for easy sharing
Compress-Archive -Path "dist/PRO-CULL-v1-Windows" -DestinationPath "PRO-CULL-v1-Windows.zip"
```

#### Option 2: Folder Copy
- Copy entire `dist/PRO-CULL-v1-Windows/` folder to shared location
- Users download and extract

#### Option 3: Cloud Storage
- Upload `dist/PRO-CULL-v1-Windows/` to OneDrive, Dropbox, Google Drive, etc.
- Share link with testers

## System Requirements

- **Windows 10 or later** (64-bit)
- **2 GB RAM** (4 GB recommended)
- **1 GB free disk space** (for extracted dependencies)
- **Internet connection** (first run only, ~500 MB download)
- **Lightroom Classic** (optional, for plugin features)

## First-Run Process

When a user runs START.bat:

1. Checks for Python virtual environment
2. Creates `.venv` folder (if needed)
3. Downloads and installs dependencies (~500 MB)
   - numpy
   - opencv-python (computer vision)
   - pillow (image processing)
   - piexif (EXIF reading)
4. Launches PRO-CULL-GUI.exe
5. Lightroom plugin is ready to use

**Total first-run time: 3-5 minutes**

## What Happens Internally

START.bat creates this structure on the user's system:

```
User's download folder/
└── PRO-CULL-v1-Windows/
    ├── .venv/                    (created after first run)
    │   ├── Scripts/
    │   │   └── python.exe
    │   ├── Lib/
    │   │   └── site-packages/
    │   └── ... (dependencies)
    ├── START.bat
    ├── PRO-CULL-GUI.exe
    ├── PRO-CULL-v1.lrplugin/
    ├── install.ps1
    ├── SETUP_GUIDE.txt
    └── README.md
```

The .venv folder is created locally - no system-wide installation.

## For Developers: Rebuilding the Package

To rebuild after code changes:

```powershell
cd J:\TOOLS\ai-photo-cull\source
.\build.ps1
```

This will:
1. Rebuild PRO-CULL-GUI.exe with latest code
2. Package everything into `dist/PRO-CULL-v1-Windows/`
3. Ready for distribution

## Uninstallation

Users can completely remove PRO-CULL by:

1. Delete the `PRO-CULL-v1-Windows/` folder
2. (Optional) Remove plugin from Lightroom: File > Plug-in Manager > Remove

No registry entries, no system-wide installation - completely clean.

## Testing Checklist

Before distributing to photographers:

- [ ] START.bat launches without errors
- [ ] PRO-CULL-GUI.exe opens after setup
- [ ] Can browse to a test photo folder
- [ ] Can analyze sample images
- [ ] Quality scores appear correctly
- [ ] EXIF details display
- [ ] (If testing Lightroom) Plugin installs successfully
- [ ] (If testing Lightroom) Settings dialog appears
- [ ] (If testing Lightroom) Ratings apply to images

## Support Resources

For testers who encounter issues:

1. **SETUP_GUIDE.txt** - Troubleshooting section
2. **README.md** - Technical documentation
3. **Start again** - Running START.bat a second time often fixes issues
4. **Run as Admin** - Right-click START.bat > Run as Administrator

## Version Info

- **Package**: PRO-CULL v1
- **Built**: December 31, 2025
- **Python**: 3.12.x (bundled in .venv)
- **GUI Framework**: tkinter
- **Lightroom Support**: Lightroom Classic
- **Target OS**: Windows 10+

## Notes for Photographers

- ✅ No coding knowledge required
- ✅ No command-line usage required
- ✅ Safe to run multiple times
- ✅ Can reinstall without issues
- ✅ Completely uninstallable
- ✅ Works offline after first setup
- ✅ All metadata non-destructive (XMP sidecars)

---

**Ready to distribute! Share `dist/PRO-CULL-v1-Windows/` with testers.**