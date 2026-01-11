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
                # Map exiftool keys to our standardized keys expected by GUI
                mapping = {
                    "Model": "camera_model",
                    "LensModel": "lens_model",
                    "FNumber": "aperture",
                    "ExposureTime": "shutter",
                    "ISO": "iso",
                    "DateTimeOriginal": "datetime",
                    "FocalLength": "focal_length",
                    "ExposureBiasValue": "exposure_bias",
                }
                for et_key, our_key in mapping.items():
                    if et_key in raw:
                        # Convert numeric values if needed
                        val = raw[et_key]
                        if our_key == "shutter" and isinstance(val, (int, float)):
                            data[our_key] = float(val)
                        elif our_key == "aperture" and isinstance(val, (int, float)):
                            data[our_key] = float(val)
                        elif our_key == "focal_length" and isinstance(val, str):
                            # ExifTool often returns "35.0 mm", strip " mm"
                            try:
                                data[our_key] = float(val.replace(" mm", ""))
                            except:
                                data[our_key] = val
                        elif our_key == "iso":
                            try:
                                data[our_key] = int(val)
                            except:
                                data[our_key] = val
                        else:
                            data[our_key] = val
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
        
        # Helper to safely parse float
        def _to_float(v):
            if isinstance(v, (int, float)): return float(v)
            if isinstance(v, tuple) and len(v) == 2 and v[1] != 0: return v[0] / v[1]
            return None

        # Map Pillow keys to standardized keys
        # Model
        if "Model" in tagmap:
            data["camera_model"] = str(tagmap["Model"]).strip()
        
        # Lens
        if "LensModel" in tagmap:
            data["lens_model"] = str(tagmap["LensModel"]).strip()
            
        # DateTime
        if "DateTimeOriginal" in tagmap:
            data["datetime"] = str(tagmap["DateTimeOriginal"])
        elif "DateTime" in tagmap:
            data["datetime"] = str(tagmap["DateTime"])
            
        # ISO
        if "ISOSpeedRatings" in tagmap:
            data["iso"] = int(tagmap["ISOSpeedRatings"])
            
        # Aperture (FNumber)
        if "FNumber" in tagmap:
            data["aperture"] = _to_float(tagmap["FNumber"])
            
        # Shutter (ExposureTime)
        if "ExposureTime" in tagmap:
            data["shutter"] = _to_float(tagmap["ExposureTime"])
            
        # FocalLength
        if "FocalLength" in tagmap:
            data["focal_length"] = _to_float(tagmap["FocalLength"])
            
        # ExposureBias
        if "ExposureBiasValue" in tagmap:
            data["exposure_bias"] = _to_float(tagmap["ExposureBiasValue"])

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
