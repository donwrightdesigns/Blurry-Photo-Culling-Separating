#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
XMP sidecar writer for PRO-CULL scores.

Writes rating, label, and custom PRECURSOR fields to .xmp sidecar files.
Lightroom/Bridge/Photo Mechanic will read these on import or sync.
"""

import os
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

# XMP namespaces
XMP_NS = {
    "x": "adobe:ns:meta/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp": "http://ns.adobe.com/xap/1.0/",
    "xmpMM": "http://ns.adobe.com/xap/1.0/mm/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "photoshop": "http://ns.adobe.com/photoshop/1.0/",
    "precursor": "http://ns.dwd.com/precursor/1.0/",
}

# Register namespaces
for prefix, uri in XMP_NS.items():
    ET.register_namespace(prefix, uri)


def _label_to_photoshop_urgency(label: str) -> Optional[int]:
    """Map color label to Photoshop Urgency (used by some apps)."""
    mapping = {"Red": 1, "Yellow": 2, "Green": 3, "Blue": 4, "Purple": 5}
    return mapping.get(label)


def write_xmp_sidecar(
    image_path: str,
    rating: int,
    label: str,
    quality_score: float,
    blur_score: float,
    composition_score: Optional[float],
    lighting_score: Optional[float],
    noise_score: Optional[float],
    collection: str,
    overwrite: bool = False,
) -> str:
    """
    Write or update XMP sidecar for an image.
    
    Returns the path to the XMP file.
    """
    image_path = Path(image_path)
    xmp_path = image_path.with_suffix(".xmp")
    
    # Check if sidecar exists
    if xmp_path.exists() and not overwrite:
        # Parse existing and update
        tree = ET.parse(xmp_path)
        root = tree.getroot()
    else:
        # Create new XMP structure
        root = ET.Element(f"{{{XMP_NS['x']}}}xmpmeta")
        root.set(f"{{{XMP_NS['x']}}}xmptk", "PRO-CULL v1")
        
        rdf = ET.SubElement(root, f"{{{XMP_NS['rdf']}}}RDF")
        desc = ET.SubElement(rdf, f"{{{XMP_NS['rdf']}}}Description")
        desc.set(f"{{{XMP_NS['rdf']}}}about", "")
    
    # Find or create Description element
    rdf = root.find(f".//{{{XMP_NS['rdf']}}}RDF")
    if rdf is None:
        rdf = ET.SubElement(root, f"{{{XMP_NS['rdf']}}}RDF")
    
    desc = rdf.find(f"{{{XMP_NS['rdf']}}}Description")
    if desc is None:
        desc = ET.SubElement(rdf, f"{{{XMP_NS['rdf']}}}Description")
        desc.set(f"{{{XMP_NS['rdf']}}}about", "")
    
    # Set standard XMP rating (1-5 stars, 0 = unrated, -1 = rejected)
    desc.set(f"{{{XMP_NS['xmp']}}}Rating", str(rating))
    
    # Set color label via photoshop:Urgency or xmp:Label
    desc.set(f"{{{XMP_NS['xmp']}}}Label", label)
    
    # Set PRECURSOR custom fields
    desc.set(f"{{{XMP_NS['precursor']}}}QualityScore", f"{quality_score:.2f}")
    desc.set(f"{{{XMP_NS['precursor']}}}BlurScore", f"{blur_score:.2f}")
    if composition_score is not None:
        desc.set(f"{{{XMP_NS['precursor']}}}CompositionScore", f"{composition_score:.2f}")
    if lighting_score is not None:
        desc.set(f"{{{XMP_NS['precursor']}}}LightingScore", f"{lighting_score:.2f}")
    if noise_score is not None:
        desc.set(f"{{{XMP_NS['precursor']}}}NoiseScore", f"{noise_score:.2f}")
    desc.set(f"{{{XMP_NS['precursor']}}}Collection", collection)
    
    # Write XMP file
    tree = ET.ElementTree(root)
    with open(xmp_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(f, encoding="unicode" if hasattr(f, 'mode') else "UTF-8", xml_declaration=False)
    
    return str(xmp_path)


def get_xmp_path(image_path: str) -> Path:
    """Return the expected XMP sidecar path for an image."""
    return Path(image_path).with_suffix(".xmp")
