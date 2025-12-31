#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Lighting analysis (fast, deterministic):
- Resize to max 1600 px long edge for consistency
- Highlight/shadow clipping fractions
- Midtone exposure balance
- Color cast distance in LAB
Returns dict with exposure_score, highlight_clip, shadow_clip, color_cast_score.
"""

import cv2
import numpy as np


def evaluate_lighting(image_path: str) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        return {
            "exposure_score": 0.0,
            "highlight_clip": 0.0,
            "shadow_clip": 0.0,
            "color_cast_score": 0.0,
        }

    h, w = img.shape[:2]
    if max(h, w) > 1600:
        scale = 1600.0 / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    Lf = L.astype(np.float32) / 255.0

    shadow_clip = float((Lf < 0.02).mean())
    highlight_clip = float((Lf > 0.98).mean())

    mid = float(((Lf > 0.15) & (Lf < 0.85)).mean())
    exposure_score = np.clip(100.0 * (mid - 0.5 * (shadow_clip + highlight_clip)), 0.0, 100.0)

    cast_distance = float(np.sqrt((A.mean() - 128.0) ** 2 + (B.mean() - 128.0) ** 2))
    color_cast_score = float(np.clip(100.0 - cast_distance / 3.0, 0.0, 100.0))

    return {
        "exposure_score": round(float(exposure_score), 2),
        "highlight_clip": round(highlight_clip, 4),
        "shadow_clip": round(shadow_clip, 4),
        "color_cast_score": round(color_cast_score, 2),
    }
