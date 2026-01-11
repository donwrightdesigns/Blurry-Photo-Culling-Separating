#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Robust EXIF extraction using PyExifTool for professional RAW+JPG workflows.
Falls back to Pillow if ExifTool is unavailable.
"""

import subprocess
import json
from typing import Any, Dict
from PIL import Image, ExifTags
import pathlib

# Check if exiftool is available
EXIFTOOL_AVAILABLE = False
try:
    result = subprocess.run(["exiftool", "-ver"], capture_output=True, text=True, timeout=2)
    if result.returncode == 0:
        EXIFTOOL_AVAILABLE = True
except (FileNotFoundError, subprocess.TimeoutExpired):
    pass


def _exiftool_extract(image_path: str) -> Dict[str, Any]:
    """Extract EXIF using exiftool CLI (most reliable for RAW files)."""
    data: Dict[str, Any] = {}
    try:
        # Run exiftool with JSON output
        result = subprocess.run(
            ["exiftool", "-j", "-Model", "-LensModel", "-FNumber", "-ExposureTime", 
             "-ISO", "-DateTimeOriginal", "-FocalLength", "-ExposureBiasValue", 
             image_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            exif_list = json.loads(result.stdout)
            if exif_list:
                raw = exif_list[0]
                # Map exiftool keys to our standardized keys
                mapping = {
                    "Model": "Model",
                    "LensModel": "LensModel",
                    "FNumber": "FNumber",
                    "ExposureTime": "ExposureTime",
                    "ISO": "ISOSpeedRatings",  # ExifTool uses "ISO"
                    "DateTimeOriginal": "DateTimeOriginal",
                    "FocalLength": "FocalLength",
                    "ExposureBiasValue": "ExposureBiasValue",
                }
                for et_key, our_key in mapping.items():
                    if et_key in raw:
                        data[our_key] = raw[et_key]
    except Exception:
        pass
    return data


def _pillow_extract(image_path: str) -> Dict[str, Any]:
    """Extract EXIF using Pillow (works for JPG/TIFF, but not RAW)."""
    data: Dict[str, Any] = {}
    try:
        img = Image.open(image_path)
        exif = img._getexif() or {}
        tagmap = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        wanted = [
            "Model",
            "LensModel",
            "FNumber",
            "ExposureTime",
            "ISOSpeedRatings",
            "DateTimeOriginal",
            "FocalLength",
            "ExposureBiasValue",
        ]
        for key in wanted:
            if key in tagmap:
                data[key] = tagmap[key]
    except Exception:
        pass
    return data


def extract_exif(image_path: str) -> Dict[str, Any]:
    """Extract EXIF data. Prefers ExifTool for RAW files, falls back to Pillow."""
    path = pathlib.Path(image_path)
    ext_lower = path.suffix.lower()
    
    # For RAW files, always use exiftool if available
    raw_exts = {".nef", ".cr2", ".cr3", ".arw", ".dng", ".raf", ".orf", ".rw2"}
    if ext_lower in raw_exts and EXIFTOOL_AVAILABLE:
        return _exiftool_extract(image_path)
    
    # For JPG/TIFF, try Pillow first (faster), fallback to exiftool
    data = _pillow_extract(image_path)
    if not data and EXIFTOOL_AVAILABLE:
        data = _exiftool_extract(image_path)
    
    return data
