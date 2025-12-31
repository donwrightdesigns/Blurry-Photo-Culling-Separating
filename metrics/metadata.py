#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Lightweight EXIF extraction using Pillow.
Returns a subset of fields useful for contextual thresholds.
"""

from typing import Any, Dict

from PIL import Image, ExifTags


def extract_exif(image_path: str) -> Dict[str, Any]:
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
