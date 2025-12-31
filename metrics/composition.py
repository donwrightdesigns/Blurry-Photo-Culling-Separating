#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Improved, production-grade composition scoring:
- Resize to consistent working resolution
- Gradient magnitude saliency
- Center-of-mass (COM) in normalized coordinates
- Gaussian rule-of-thirds scoring
- Soft symmetry scoring
- Low-gradient fallback
Returns a float in [0, 100].
"""

import cv2
import numpy as np


def _resize_for_cv(img, max_dim=1024):
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return img
    if w >= h:
        new_w = max_dim
        new_h = int(h * (max_dim / w))
    else:
        new_h = max_dim
        new_w = int(w * (max_dim / h))
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    return cv2.GaussianBlur(mag, (5, 5), 0)


def evaluate_composition(image_path: str) -> float:
    img = cv2.imread(image_path)
    if img is None:
        return 0.0

    # Normalize resolution for consistent scoring
    img = _resize_for_cv(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Gradient saliency map
    mag = _gradient_magnitude(gray)
    mean_grad = float(mag.mean())

    # Low-gradient fallback (fog, bokeh, soft portraits)
    if mean_grad < 0.01:
        return 50.0

    h, w = mag.shape
    total = mag.sum() + 1e-6
    ys, xs = np.indices(mag.shape)

    # Center of mass (normalized)
    cx = float((mag * xs).sum() / total) / w
    cy = float((mag * ys).sum() / total) / h

    # Rule-of-thirds intersections (normalized)
    thirds = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]

    # Distance to nearest thirds point
    dist = min(np.hypot(cx - tx, cy - ty) for tx, ty in thirds)

    # Gaussian falloff for thirds scoring
    sigma = 0.15
    thirds_score = 100.0 * np.exp(-((dist ** 2) / (2 * sigma ** 2)))
    thirds_score = float(np.clip(thirds_score, 0.0, 100.0))

    # Symmetry scoring (soft influence)
    left = mag[:, : w // 2].sum()
    right = mag[:, w - w // 2 :].sum()
    sym_ratio = 1.0 - abs(left - right) / (left + right + 1e-6)
    sym_score = float(np.clip(sym_ratio * 100.0, 0.0, 100.0))

    # Weighted final composition score
    return float(0.85 * thirds_score + 0.15 * sym_score)
