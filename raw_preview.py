#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAW preview extractor.

Extracts embedded JPEG preview from RAW files for fast assessment.
Falls back to full decode if preview not available.

Requires: rawpy (optional dependency)
"""

import io
import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

# RAW extensions we support
RAW_EXTENSIONS = {
    ".nef",   # Nikon
    ".cr2",   # Canon
    ".cr3",   # Canon (newer)
    ".arw",   # Sony
    ".dng",   # Adobe DNG
    ".raf",   # Fujifilm
    ".orf",   # Olympus
    ".rw2",   # Panasonic
    ".pef",   # Pentax
    ".srw",   # Samsung
    ".raw",   # Generic
}

# Add uppercase versions
RAW_EXTENSIONS = RAW_EXTENSIONS | {ext.upper() for ext in RAW_EXTENSIONS}


def is_raw_file(path: str) -> bool:
    """Check if file is a RAW image."""
    return Path(path).suffix in RAW_EXTENSIONS


def extract_preview(raw_path: str) -> Optional[np.ndarray]:
    """
    Extract embedded JPEG preview from RAW file.
    
    Returns BGR numpy array suitable for cv2, or None if extraction fails.
    """
    try:
        import rawpy
    except ImportError:
        logging.warning("rawpy not installed. Cannot extract RAW preview. Install with: pip install rawpy")
        return None
    
    try:
        with rawpy.imread(raw_path) as raw:
            # Try to get embedded thumbnail/preview (fastest)
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    # Decode JPEG to numpy array
                    arr = np.frombuffer(thumb.data, dtype=np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        logging.debug(f"Extracted JPEG preview from {raw_path}")
                        return img
                elif thumb.format == rawpy.ThumbFormat.BITMAP:
                    # Already RGB bitmap
                    img = cv2.cvtColor(thumb.data, cv2.COLOR_RGB2BGR)
                    logging.debug(f"Extracted bitmap preview from {raw_path}")
                    return img
            except rawpy.LibRawNoThumbnailError:
                logging.debug(f"No embedded thumbnail in {raw_path}, falling back to decode")
            except Exception as e:
                logging.debug(f"Thumbnail extraction failed for {raw_path}: {e}")
            
            # Fallback: decode RAW (slower but works)
            rgb = raw.postprocess(
                use_camera_wb=True,
                half_size=True,  # Faster, good enough for assessment
                no_auto_bright=True,
            )
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            logging.debug(f"Decoded RAW preview from {raw_path}")
            return img
            
    except Exception as e:
        logging.error(f"Failed to extract preview from {raw_path}: {e}")
        return None


def read_image_or_raw(path: str) -> Optional[np.ndarray]:
    """
    Read image file, handling both standard formats and RAW.
    
    Returns BGR numpy array or None.
    """
    if is_raw_file(path):
        return extract_preview(path)
    else:
        return cv2.imread(path)
