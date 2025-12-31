"""
scoring.py

Combines all metric scores into a single technical score.
Designed to be:
- deterministic
- fast
- EXIF-aware but EXIF-agnostic (works even with missing EXIF)
"""

from typing import Any, Dict
import numpy as np
import cv2

from metrics import (
    evaluate_composition,
    evaluate_lighting,
    estimate_noise_score,
    extract_exif,
)
from process import score_blur, lighting_to_scalar  # reuse logic


def _load_image_bgr(path: str):
    arr = cv2.imread(path)
    return arr


def score_image(
    image_path: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Returns a dict:
    {
        "path": str,
        "scores": {
            "composition": float,
            "lighting": float,
            "blur": float,
            "noise": float,
            "exposure": float,
            "overall": float,
        },
        "exif": { ... normalized fields ... }
    }
    """
    exif = extract_exif(image_path)
    arr = _load_image_bgr(image_path)
    if arr is None:
        return {
            "path": image_path,
            "scores": {},
            "exif": exif,
        }

    # Metrics (normalize to 0-1 for this pipeline)
    comp = evaluate_composition(image_path) / 100.0
    light_dict = evaluate_lighting(image_path)
    light = lighting_to_scalar(light_dict) / 100.0
    iso = exif.get("iso") or 100.0
    blur = score_blur(lap_var=np.var(cv2.Laplacian(cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY), cv2.CV_64F)),
                      shutter=exif.get("shutter"),
                      focal_length=exif.get("focal_length")) / 100.0
    noise = estimate_noise_score(image_path, iso=iso) / 100.0

    # Weights from config or defaults
    w_comp = config.get("weight_composition", 0.25)
    w_light = config.get("weight_lighting", 0.20)
    w_blur = config.get("weight_blur", 0.25)
    w_noise = config.get("weight_noise", 0.15)
    w_expo = config.get("weight_exposure", 0.15)

    # Exposure placeholder: reuse lighting mid component for now
    expo = light

    overall = (
        comp * w_comp
        + light * w_light
        + blur * w_blur
        + noise * w_noise
        + expo * w_expo
    )
    overall = float(np.clip(overall, 0.0, 1.0))

    return {
        "path": image_path,
        "scores": {
            "composition": comp,
            "lighting": light,
            "blur": blur,
            "noise": noise,
            "exposure": expo,
            "overall": overall,
        },
        "exif": exif,
    }
