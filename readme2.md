# Pro-Culling-Engine v0.5

A deterministic, EXIF-aware but EXIF-agnostic technical culling core,
designed to be wrapped by a Lightroom plugin.

## Features

- Pure Python core (Pillow + NumPy + OpenCV)
- Fast, deterministic metrics:
  - Composition
  - Lighting
  - Blur
  - Noise
  - Exposure
- EXIF used when available, but never required
- Designed for future Lightroom integration via CLI or local service

## Install

```bash
pip install pillow numpy opencv-python
