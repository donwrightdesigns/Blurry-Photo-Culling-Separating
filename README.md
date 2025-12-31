# Blur Detection w optional img SUB-DIRECTORY move
Python script, modified to now cull the images based on results (Add to subdirectories) 

Personally, I use this script for preparing datasets for photogrammetry and Nerf or Gaussian Splat creation

Dependencies: numpy, opencv-python, Pillow.

**Optional for RAW support:** `pip install rawpy`
- Extracts embedded JPEG preview from RAW files (NEF, CR2, ARW, DNG, etc.)
- Falls back to half-size decode if no preview available
- XMP sidecars are written next to RAW files

Quick venv install (no conda):

```bash
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

## Scoring Guide

All metrics return scores from **0–100** (higher is better).

| Metric | What it measures | 0 | 50 | 100 |
|--------|------------------|---|----|----|  
| **Blur** | Sharpness (Laplacian variance, EXIF-adjusted) | Very blurry | Acceptable | Tack sharp |
| **Composition** | Rule-of-thirds + symmetry | Subject at edge/corner | Neutral | Subject on power point |
| **Lighting** | Exposure balance, clipping, color cast | Severely over/underexposed | Average exposure | Well-balanced, no clipping |
| **Noise** | ISO-adjusted noise estimate | Very noisy | Moderate | Clean |
| **Exposure** | (Proxy: same as lighting for now) | — | — | — |

### Quality Score
Weighted combination of enabled metrics (default weights):
- Blur: 40%
- Composition: 30%
- Lighting: 20%
- Noise: 10%

### Rating/Label/Collection Mapping
| Quality Score | Rating | Label | Collection |
|---------------|--------|-------|------------|
| < 30 (or blurry) | 1★ | Red | PRECURSOR Rejects |
| 30–49 | 2★ | Yellow | PRECURSOR Review |
| 50–64 | 3★ | Yellow | PRECURSOR Review |
| 65–79 | 4★ | Green | PRECURSOR Keepers |
| 80–100 | 5★ | Green | PRECURSOR Keepers |

## Output Options

### XMP Sidecars (recommended)
```bash
python process.py -i "D:\Photos" --all-metrics --write-xmp
```
Writes `.xmp` sidecar files next to each image with:
- `xmp:Rating` (1-5 stars)
- `xmp:Label` (Red/Yellow/Green)
- Custom `precursor:*` fields (QualityScore, BlurScore, etc.)

Lightroom/Bridge/Photo Mechanic will read these on import or folder sync.

Use `--overwrite-xmp` to replace existing sidecars (default: merge/update).

### JSON/TSV (for scripting)
```bash
python process.py -i "D:\Photos" --all-metrics --save-path results.json --tsv-path results.tsv
```

## Lightroom Classic plugin (PRO-CULL v1)
- Plugin bundle: `PRO-CULL-v1.lrplugin/`
- Runs `process.py` on selected photos, applies ratings/labels/collections directly to catalog.
- Defaults to `python` on PATH (so activate your venv first).
- If you move the plugin outside the repo, update `defaultPython` and script path in `CullSelected.lua`.

The repository has a script, `process.py` which lets us run on single images or directories of images. The blur detection method is highly dependent on the size of the image being processed. To get consistent scores we fix the image size to HD, to disable this use  `--variable-size`. The script has options to, 

```bash
# run on a single image
python process.py -i input_image.png

# run on a directory of images
python process.py -i input_directory/ 

# or both! 
python process.py -i input_directory/ other_directory/ input_image.png
```

. In addition to logging whether an image is blurry or not, we can also,

```bash
# save this information to json
python process.py -i input_directory/ -s results.json

# display blur-map image
python process.py -i input_directory/ -d
```
The saved json file has information on how blurry an image is, the higher the value, the less blurry the image.

```json
{
    "images": ["/Users/demo_user/Pictures/Flat/"],
    "fix_size": true,
    "results": [
        {
            "blurry": false,
            "input_path": "/Users/demo_user/Pictures/Flat/IMG_1666.JPG",
            "score": 6984.8082115095549
        },
    ],
    "threshold": 100.0
}
```

This is based upon the blogpost [Blur Detection With Opencv](https://www.pyimagesearch.com/2015/09/07/blur-detection-with-opencv/) by Adrian Rosebrock.


#*NEW* To enable moving blurry images, add the --move-blurry flag:

```bash
python process.py -i s:\test --save-path results_moved.json --move-blurry
```

If you want to specify a different subdirectory name than "blurry_images":

```bash
python process.py -i s:\test --save-path results_moved.json --move-blurry --blurry-subdir "needs_review"
```

