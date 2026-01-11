import sys
import argparse
import logging
import pathlib
import json
import shutil
import math

import cv2
import numpy as np

from blur_detection import estimate_blur, fix_image_size, pretty_blur_map
from metrics import (
    evaluate_composition,
    evaluate_lighting,
    estimate_noise_score,
    extract_exif,
)
from xmp_writer import write_xmp_sidecar
from raw_preview import RAW_EXTENSIONS, read_image_or_raw


def parse_args():
    parser = argparse.ArgumentParser(
        description="Multi-metric technical culling (blur, composition, lighting, noise, EXIF-aware)."
    )
    parser.add_argument(
        "-i", "--images", type=str, nargs="+", required=True, help="Image files or directories (recursed)."
    )
    parser.add_argument("--no-recursive", action="store_true", help="Do not recurse into subdirectories.")
    parser.add_argument("-s", "--save-path", type=str, default=None, help="Path to save JSON results.")
    parser.add_argument("--tsv-path", type=str, default=None, help="Optional TSV output for Lightroom plugin.")

    parser.add_argument("-t", "--threshold", type=float, default=100.0, help="Blur threshold (Laplacian var).")
    parser.add_argument("-f", "--variable-size", action="store_true", help="Do NOT fix image size before blur scoring.")

    parser.add_argument("--all-metrics", action="store_true", help="Enable all metrics.")
    parser.add_argument("--composition", action="store_true", help="Compute composition score.")
    parser.add_argument("--lighting", action="store_true", help="Compute lighting metrics.")
    parser.add_argument("--noise", action="store_true", help="Compute noise score.")
    parser.add_argument("--metadata", action="store_true", help="Extract EXIF metadata.")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    parser.add_argument("-d", "--display", action="store_true", help="Display images and blur maps.")

    parser.add_argument("--move-blurry", action="store_true", help="Move blurry images to a subdirectory.")
    parser.add_argument(
        "--blurry-subdir",
        type=str,
        default="blurry_images",
        help="Subdirectory name for blurry images (created next to originals).",
    )

    parser.add_argument(
        "--write-xmp",
        action="store_true",
        help="Write XMP sidecar files with ratings/labels (non-destructive, recommended).",
    )
    parser.add_argument(
        "--overwrite-xmp",
        action="store_true",
        help="Overwrite existing XMP sidecars (default: merge/update).",
    )

    return parser.parse_args()


def find_images(image_paths, img_extensions=None, recursive=True):
    if img_extensions is None:
        img_extensions = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"]
        img_extensions += list(RAW_EXTENSIONS)  # Add RAW support
    img_extensions += [i.upper() for i in img_extensions]

    for path_str in image_paths:
        path = pathlib.Path(path_str)
        if path.is_file():
            if path.suffix not in img_extensions:
                logging.info(f"{path.suffix} is not recognized, skipping {path}")
                continue
            yield path
        elif path.is_dir():
            for ext in img_extensions:
                if recursive:
                    yield from path.rglob(f"*{ext}")
                else:
                    yield from path.glob(f"*{ext}")
        else:
            logging.warning(f"Provided path '{path}' is neither file nor directory. Skipping.")


def score_blur(lap_var, shutter=None, focal_length=None, safety_factor=1.5):
    """
    Laplacian variance -> 0-100, EXIF-aware tolerance for slow shutter vs focal length.
    """
    L_ref = 200.0
    sharp = 100.0 * (math.log(lap_var + 1.0) / math.log(L_ref + 1.0))
    sharp = float(np.clip(sharp, 0, 100))

    if shutter is not None and focal_length is not None and focal_length > 0:
        t_safe = 1.0 / (safety_factor * focal_length)
        if shutter > t_safe:
            adj = 10.0 * ((shutter - t_safe) / t_safe)
            sharp += adj

    return float(np.clip(sharp, 0, 100))


def lighting_to_scalar(light_dict: dict) -> float:
    exp_score = light_dict.get("exposure_score", 50.0)
    clip_penalty = 100.0 * (light_dict.get("highlight_clip", 0) + light_dict.get("shadow_clip", 0))
    cast_score = light_dict.get("color_cast_score", 50.0)
    score = exp_score - clip_penalty * 0.5 + 0.2 * cast_score
    return float(np.clip(score, 0, 100))


def quality_score(metric_scores: dict, metric_weights: dict, enabled: list):
    """
    Compute weighted score over enabled metrics only.
    metric_scores: dict of name -> 0-100 or None
    metric_weights: dict of name -> weight
    enabled: list of metric names to include
    """
    contribs = []
    weights = []
    for m in enabled:
        val = metric_scores.get(m)
        w = metric_weights.get(m, 0)
        if val is None or w == 0:
            continue
        contribs.append(val * w)
        weights.append(w)
    if not contribs or sum(weights) == 0:
        return 0.0
    return float(sum(contribs) / sum(weights))


def rating_for_score(score, blurry):
    if blurry or score < 30:
        return 1
    if score < 50:
        return 2
    if score < 65:
        return 3
    if score < 80:
        return 4
    if score < 90:
        return 5
    return 5


def label_for_score(score, blurry):
    if blurry or score < 30:
        return "Red"
    if score < 50:
        return "Yellow"
    if score < 65:
        return "Yellow"
    if score < 80:
        return "Green"
    return "Green"


def collection_for_score(score, blurry):
    if blurry or score < 30:
        return "PRECURSOR Rejects"
    if score < 65:
        return "PRECURSOR Review"
    return "PRECURSOR Keepers"


def main():
    args = parse_args()

    logging.basicConfig(
        format="%(asctime)s : %(levelname)s : %(module)s : %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stdout,
    )

    enable_comp = args.all_metrics or args.composition
    enable_light = args.all_metrics or args.lighting
    enable_noise = args.all_metrics or args.noise
    enable_meta = args.all_metrics or args.metadata or enable_noise

    fix_size = not args.variable_size
    if args.save_path:
        save_path = pathlib.Path(args.save_path)
        if save_path.suffix.lower() != ".json":
            save_path = save_path.with_suffix(".json")
    else:
        save_path = None

    # Collect upfront for progress feedback
    recursive = not args.no_recursive
    images = list(find_images(args.images, recursive=recursive))
    total_images = len(images)
    logging.info(f"Discovered {total_images} images to process.")

    results = []
    tsv_lines = []
    moved_count = 0
    error_moving_count = 0
    processed_image_count = 0

    for idx, image_path in enumerate(images, start=1):
        processed_image_count += 1
        logging.info(f"[{idx}/{total_images}] Processing {image_path}")
        logging.debug(f"Reading image: {image_path}")
        image = read_image_or_raw(str(image_path))
        if image is None:
            logging.warning(f"Failed to read image from {image_path}; skipping!")
            continue

        if fix_size:
            processed_image_for_blur = fix_image_size(image.copy())
        else:
            processed_image_for_blur = image.copy()

        blur_map, lap_var, blurry_flag = estimate_blur(processed_image_for_blur, threshold=args.threshold)

        exif_data = extract_exif(str(image_path)) if enable_meta else {}
        shutter = exif_data.get("shutter")
        focal = exif_data.get("focal_length")
        iso = exif_data.get("iso") or 100.0
        blur_score = score_blur(lap_var, shutter, focal)

        comp_score = evaluate_composition(str(image_path)) if enable_comp else None
        light_dict = evaluate_lighting(str(image_path)) if enable_light else None
        light_score = lighting_to_scalar(light_dict) if light_dict else None
        noise_score = estimate_noise_score(str(image_path), iso=iso) if enable_noise else None
        exposure_score = light_score  # proxy for now

        metric_scores = {
            "blur": blur_score,
            "composition": comp_score,
            "lighting": light_score,
            "noise": noise_score,
            "exposure": exposure_score,
        }
        metric_weights = {
            "blur": 0.40,
            "composition": 0.30,
            "lighting": 0.20,
            "noise": 0.10,
            "exposure": 0.20,
        }
        enabled_metrics = ["blur"]
        if enable_comp:
            enabled_metrics.append("composition")
        if enable_light:
            enabled_metrics.append("lighting")
            enabled_metrics.append("exposure")
        if enable_noise:
            enabled_metrics.append("noise")

        q_score = quality_score(metric_scores, metric_weights, enabled_metrics)
        rating = rating_for_score(q_score, blurry_flag)
        label = label_for_score(q_score, blurry_flag)
        collection = collection_for_score(q_score, blurry_flag)

        result = {
            "input_path": str(image_path),
            "blur_laplacian_var": float(lap_var),
            "blur_score": blur_score,
            "blurry": bool(blurry_flag),
            "composition_score": comp_score,
            "lighting": light_dict,
            "lighting_score": light_score,
            "noise_score": noise_score,
            "quality_score": q_score,
            "rating": rating,
            "label": label,
            "collection": collection,
            "exif": exif_data if enable_meta else {},
        }
        results.append(result)

        tsv_lines.append(
            f"{image_path}\t{q_score:.2f}\t{rating}\t{label}\t{collection}\t{int(blurry_flag)}\n"
        )

        if args.write_xmp:
            try:
                xmp_path = write_xmp_sidecar(
                    image_path=str(image_path),
                    rating=rating,
                    label=label,
                    quality_score=q_score,
                    blur_score=blur_score,
                    composition_score=comp_score,
                    lighting_score=light_score,
                    noise_score=noise_score,
                    collection=collection,
                    overwrite=args.overwrite_xmp,
                )
                logging.debug(f"Wrote XMP sidecar: {xmp_path}")
            except Exception as e:
                logging.error(f"Failed to write XMP for {image_path}: {e}")

        if args.move_blurry and blurry_flag:
            try:
                original_image_dir = image_path.parent
                target_blurry_dir = original_image_dir / args.blurry_subdir
                target_blurry_dir.mkdir(parents=True, exist_ok=True)
                destination_path = target_blurry_dir / image_path.name
                if destination_path.exists():
                    logging.warning(f"File '{destination_path}' already exists. Skipping move for '{image_path}'.")
                elif image_path.exists():
                    shutil.move(str(image_path), str(destination_path))
                    logging.info(f"MOVED blurry image: '{image_path}' -> '{destination_path}'")
                    moved_count += 1
                else:
                    logging.warning(f"Source image '{image_path}' not found for moving.")
            except Exception as e:
                logging.error(f"Error moving blurry image '{image_path}' to '{destination_path}': {e}")
                error_moving_count += 1

        if args.display:
            cv2.imshow("Input Image", image)
            cv2.imshow("Blur Map (Processed)", pretty_blur_map(blur_map))
            key = cv2.waitKey(0)
            if key == ord("q"):
                logging.info('Exiting due to "q" key press...')
                cv2.destroyAllWindows()
                break
            cv2.destroyAllWindows()

    if save_path is not None:
        logging.info(f"Saving JSON results to {save_path}")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        output_data = {
            "source_image_paths_or_dirs": args.images,
            "blur_threshold_used": args.threshold,
            "image_size_fixed_for_scoring": fix_size,
            "recursive": recursive,
            "weights": {"blur": 0.4, "composition": 0.3, "lighting": 0.2, "noise": 0.1},
            "results": results,
        }
        if args.move_blurry:
            output_data["blurry_images_intended_subdir"] = args.blurry_subdir
            output_data["blurry_images_successfully_moved"] = moved_count
            if error_moving_count > 0:
                output_data["blurry_images_move_errors"] = error_moving_count
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        logging.info(f"Saved results to {save_path}")

    if args.tsv_path:
        tsv_path = pathlib.Path(args.tsv_path)
        tsv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tsv_path, "w", encoding="utf-8") as f:
            f.write("path\tquality_score\trating\tlabel\tcollection\tblurry\n")
            for line in tsv_lines:
                f.write(line)
        logging.info(f"Saved TSV results to {tsv_path}")

    logging.info(f"Processing complete. Total images considered: {processed_image_count}.")
    if args.move_blurry:
        logging.info(f"Total blurry images moved: {moved_count}")
        if error_moving_count > 0:
            logging.warning(f"Errors encountered while moving images: {error_moving_count}")


if __name__ == "__main__":
    main()
