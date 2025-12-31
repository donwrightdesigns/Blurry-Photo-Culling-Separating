#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Lightweight EXIF extraction with friendly normalization.
"""

from typing import Any, Dict, Optional
from PIL import Image, ExifTags


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (tuple, list)) and len(value) == 2:
            num, den = value
            if den:
                return float(num) / float(den)
            return float(num)
        if isinstance(value, str) and "/" in value:
            num, den = value.split("/")
            return float(num) / float(den)
        if isinstance(value, str):
            cleaned = (
                value.replace("mm", "")
                .replace("MM", "")
                .replace("f/", "")
                .strip()
            )
            if cleaned:
                return float(cleaned)
    except Exception:
        return None
    return None


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).split("\x00")[0].strip()


def extract_exif(image_path: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "camera_model": "",
        "lens_model": "",
        "shutter": None,
        "aperture": None,
        "iso": None,
        "focal_length": None,
        "exposure_bias": None,
        "datetime": "",
        "vr_enabled": None,
        "focus_distance": None,
        "focus_success": None,
        "subject_motion": None,
        "subject_detection": None,
        "roll_angle": None,
        "pitch_angle": None,
    }
    try:
        img = Image.open(image_path)
        exif_raw = img._getexif() or {}
        tagmap = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}

        data["camera_model"] = _clean_str(tagmap.get("Model"))
        data["lens_model"] = _clean_str(tagmap.get("LensModel"))
        data["datetime"] = _clean_str(
            tagmap.get("DateTimeOriginal")
            or tagmap.get("CreateDate")
            or tagmap.get("DateTime")
        )

        data["aperture"] = _to_float(tagmap.get("FNumber"))
        data["shutter"] = _to_float(tagmap.get("ExposureTime"))
        data["focal_length"] = _to_float(tagmap.get("FocalLength"))
        data["exposure_bias"] = _to_float(tagmap.get("ExposureBiasValue"))

        iso_candidate = (
            tagmap.get("ISOSpeedRatings")
            or tagmap.get("PhotographicSensitivity")
            or tagmap.get("ISO")
        )
        iso_val = _to_float(iso_candidate)
        data["iso"] = int(iso_val) if iso_val is not None else None

        roll = tagmap.get("RollAngle")
        pitch = tagmap.get("PitchAngle")
        data["roll_angle"] = _to_float(roll)
        data["pitch_angle"] = _to_float(pitch)

    except Exception:
        return data

    return data
