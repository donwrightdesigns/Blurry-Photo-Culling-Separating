#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Simple noise estimation:
- High-pass (Laplacian) energy normalized by luminance
- Optional ISO-aware scaling (caller can blend)
Returns 0–100 score (higher is cleaner).
"""

import cv2
import numpy as np


def estimate_noise_score(image_path: str, iso: float = 100.0) -> float:
    img = cv2.imread(image_path)
    if img is None:
        return 0.0

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = gray.astype(np.float32) / 255.0

    lap = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    noise_energy = float(np.mean(np.abs(lap)))

    # Convert to score: lower noise_energy -> higher score
    base_score = 100.0 * np.exp(-noise_energy * 40.0)

    # ISO adjustment: tolerate higher noise at high ISO
    iso_factor = np.log1p(iso) / np.log(6400 + 1)
    iso_adjust = 15.0 * (iso_factor - 0.5)  # range roughly [-7.5, +7.5]

    score = base_score + iso_adjust
    return float(np.clip(score, 0.0, 100.0))
