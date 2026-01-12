#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Robust EXIF extraction using PyExifTool for professional RAW+JPG workflows.
Falls back to Pillow if ExifTool is unavailable.
"""

import subprocess
import json
from typing import Any, Dict, Optional, Union
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
        # Request multiple variants of FocalLength to be safe
        result = subprocess.run(
            ["exiftool", "-j", "-Model", "-LensModel", "-FNumber", "-ExposureTime", 
             "-ISO", "-DateTimeOriginal", "-FocalLength", "-LensFocalLength", 
             "-FocalLengthIn35mmFormat", "-ExposureBiasValue", 
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
                    "LensFocalLength": "focal_length",
                    "FocalLengthIn35mmFormat": "focal_length",
                    "ExposureBiasValue": "exposure_bias",
                }
                for et_key, our_key in mapping.items():
                    if et_key in raw:
                        # Convert numeric values if needed
                        val = raw[et_key]
                        
                        # Special handling for FocalLength priority
                        # If we already have a value, and this is a "better" key, we might overwrite.
                        # Since we map multiple keys to 'focal_length', the LAST one visited wins 
                        # if we iterate. But insertion order of mapping dict is preserved in Python 3.7+.
                        # So: FocalLength, then LensFocalLength, then FocalLengthIn35mmFormat.
                        # This means FocalLengthIn35mmFormat (most standard for calcs) will win if present.
                        
                        if our_key in ("shutter", "aperture", "focal_length", "exposure_bias"):
                            # Robustly convert to float (handles "1/60", "35 mm", etc.)
                            f_val = _to_float(val)
                            if f_val is not None:
                                data[our_key] = f_val
                            # If conversion fails, do NOT set the key with a raw string 
                            # to avoid TypeErrors in comparisons later.
                        elif our_key == "iso":
                            # Try to convert to int, but keep as is if fails (some ISOs are weird strings like "Hi")
                            try:
                                data[our_key] = int(val)
                            except:
                                data[our_key] = val
                        else:
                            data[our_key] = val
    except Exception:
        pass
    return data


def _to_float(v: Any) -> Optional[float]:
    """Helper to safely parse float from various Pillow EXIF types."""
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, tuple) and len(v) == 2:
            # Handle rational (numerator, denominator)
            if v[1] == 0:
                return 0.0
            return float(v[0]) / float(v[1])
        if hasattr(v, 'numerator') and hasattr(v, 'denominator'):
            # Handle IFDRational
            if v.denominator == 0:
                return 0.0
            return float(v.numerator) / float(v.denominator)
        if isinstance(v, str):
            v_clean = v.strip().lower()
            # Handle units like " mm", " s"
            if v_clean.endswith(" mm"):
                v_clean = v_clean[:-3]
            elif v_clean.endswith(" s"):
                v_clean = v_clean[:-2]
                
            # Try parsing "1/60" string
            if '/' in v_clean:
                n, d = v_clean.split('/')
                return float(n) / float(d)
            return float(v_clean)
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return None


def _pillow_extract(image_path: str) -> Dict[str, Any]:
    """
    Extract EXIF using Pillow with robust fallback strategies.
    Works for JPG/TIFF/HEIC (if Pillow supports it).
    """
    data: Dict[str, Any] = {}
    try:
        img = Image.open(image_path)
        
        # Strategy 1: Modern getexif() (returns Image.Exif object)
        exif_obj = img.getexif()
        exif_data = {k: v for k, v in exif_obj.items()} if exif_obj else {}
        
        # Strategy 2: Legacy _getexif() (returns dict)
        if not exif_data and hasattr(img, "_getexif"):
            exif_data = img._getexif() or {}

        # Strategy 3: Loop over ExifTags to find named fields
        # Invert the TAGS map for easier lookup by name
        name_to_id = {v: k for k, v in ExifTags.TAGS.items()}
        
        # Helper to get value by tag ID or name
        def get_val(names):
            if isinstance(names, str): names = [names]
            for name in names:
                # Try by ID
                tid = name_to_id.get(name)
                if tid and tid in exif_data:
                    return exif_data[tid]
                # Try by iterating (slow fallback if keys aren't IDs)
                for k, v in exif_data.items():
                    if ExifTags.TAGS.get(k) == name:
                        return v
            return None

        # Extract fields
        model = get_val(["Model"])
        if model: data["camera_model"] = str(model).strip()
        
        lens = get_val(["LensModel", "LensInfo", "LensMake"])
        if lens: data["lens_model"] = str(lens).strip()
        
        dt = get_val(["DateTimeOriginal", "DateTime"])
        if dt: data["datetime"] = str(dt)
        
        iso = get_val(["ISOSpeedRatings", "ISOSpeed"])
        if iso: 
            # ISO might be a tuple
            if isinstance(iso, tuple): iso = iso[0]
            data["iso"] = int(iso)

        # Aperture: FNumber (33437) or ApertureValue (37378)
        f_num = get_val(["FNumber", "ApertureValue"])
        if f_num: data["aperture"] = _to_float(f_num)
        
        # Shutter: ExposureTime (33434) or ShutterSpeedValue (37377)
        # Note: ShutterSpeedValue is usually APEX units, ExposureTime is seconds.
        # Pillow usually returns ExposureTime as the main one.
        exp_time = get_val(["ExposureTime"])
        if exp_time: 
            data["shutter"] = _to_float(exp_time)
        else:
            # Fallback to ShutterSpeedValue (APEX) -> Seconds = 1 / 2^APEX
            ss_val = get_val(["ShutterSpeedValue"])
            if ss_val:
                apex = _to_float(ss_val)
                if apex is not None:
                    data["shutter"] = 1.0 / (2.0 ** apex)

        # Focal Length: FocalLength (37386) or FocalLengthIn35mmFilm (41989)
        focal = get_val(["FocalLengthIn35mmFilm", "FocalLength"])
        if focal: data["focal_length"] = _to_float(focal)
        
        bias = get_val(["ExposureBiasValue"])
        if bias: data["exposure_bias"] = _to_float(bias)

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
    
    # Validation: If critical fields missing, try ExifTool
    critical_missing = not (data.get("focal_length") and data.get("aperture"))
    if critical_missing and EXIFTOOL_AVAILABLE:
        # Merge, preferring ExifTool
        et_data = _exiftool_extract(image_path)
        data.update(et_data)
    
    return data
