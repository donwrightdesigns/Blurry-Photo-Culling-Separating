"""
pipeline.py

Batch scoring pipeline.

This is what a future Lightroom plugin would call:
- via CLI (passing a folder or file list)
- or via a small local service wrapper

Keeps responsibilities simple and serializable.
"""

from typing import Any, Dict, List
import os
import json

from scoring import score_image


def _iter_images(root: str, extensions=None):
    if extensions is None:
        extensions = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    extensions = {e.lower() for e in extensions}

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in extensions:
                yield os.path.join(dirpath, fname)


def score_folder(
    folder: str,
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Score all images in a folder (recursively).
    Returns a list of scoring dicts.
    """
    results = []
    for path in _iter_images(folder):
        try:
            res = score_image(path, config)
            results.append(res)
        except Exception:
            # Keep pipeline robust; in logging-enabled environments,
            # you'd log the failure instead of silently ignoring.
            continue
    return results


def save_results_json(results: List[Dict[str, Any]], output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def main():
    """
    Simple CLI entry point example.

    Usage:
        python -m pipeline /path/to/images config_example.json output.json
    """
    import sys

    if len(sys.argv) < 4:
        print(
            "Usage: python -m pipeline <folder> <config.json> <output.json>",
            flush=True,
        )
        sys.exit(1)

    folder = sys.argv[1]
    config_path = sys.argv[2]
    output_path = sys.argv[3]

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    results = score_folder(folder, config)
    save_results_json(results, output_path)
    print(f"Scored {len(results)} images. Saved to {output_path}", flush=True)


if __name__ == "__main__":
    main()
