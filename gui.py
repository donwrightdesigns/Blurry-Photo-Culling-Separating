#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Improved PRO-CULL GUI (tkinter)

Enhancements over previous version:
- Chunked processing with pause between chunks to avoid long continuous CPU/GPU spikes
- ETA estimation and richer progress HUD
- Safe, atomic move with collision handling (append suffix)
- Optional RAW preview usage toggle (uses read_image_or_raw / rawpy if available)
- Per-run summary (processed / moved / errors / elapsed) shown at completion and logged
- Non-blocking background thread for analysis; GUI remains responsive
- Robust logging to pro-cull-gui.log with minimal risk of breaking the GUI
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import json
import pathlib
import os
import cv2
import shutil
import datetime
import time
import math
from typing import List, Dict, Any, Optional

LOG_PATH = os.path.join(os.getcwd(), "pro-cull-gui.log")


def log_event(message: str) -> None:
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts} | {message}\n")
    except Exception:
        # Logging must never break the GUI
        pass


# Import local processing helpers (assumed present in repo)
from blur_detection import estimate_blur, fix_image_size, pretty_blur_map  # type: ignore
from process import (
    find_images,
    score_blur,
    lighting_to_scalar,
    quality_score,
    rating_for_score,
    label_for_score,
    collection_for_score,
)  # type: ignore
from metrics import (
    evaluate_composition,
    evaluate_lighting,
    estimate_noise_score,
    extract_exif,
)  # type: ignore

# Optional RAW preview helper (if available in repo)
try:
    from raw_preview import read_image_or_raw  # type: ignore
    RAW_PREVIEW_AVAILABLE = True
except Exception:
    RAW_PREVIEW_AVAILABLE = False


class BlurDetectorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PRECURSOR Technical Culling (BETA)")
        self.geometry("1200x760")

        # User-configurable variables
        self.image_dir = tk.StringVar()
        self.blur_threshold = tk.DoubleVar(value=100.0)
        self.reject_threshold = tk.DoubleVar(value=30.0)
        self.review_threshold = tk.DoubleVar(value=65.0)
        self.move_rejects = tk.BooleanVar(value=False)
        self.rejection_subdir = tk.StringVar(value="Blurry-Images")
        self.use_raw_preview = tk.BooleanVar(value=RAW_PREVIEW_AVAILABLE)
        self.chunk_size = tk.IntVar(value=100)
        self.pause_between_chunks = tk.DoubleVar(value=5.0)  # seconds
        self.max_images = tk.IntVar(value=0)  # 0 means no limit
        self.dry_run = tk.BooleanVar(value=False)
        
        # Additional settings synchronized from Lightroom plugin
        self.use_blur = tk.BooleanVar(value=True)
        self.use_composition = tk.BooleanVar(value=True)
        self.use_lighting = tk.BooleanVar(value=True)
        self.use_noise = tk.BooleanVar(value=True)
        self.write_xmp = tk.BooleanVar(value=True)
        self.apply_to_lightroom = tk.BooleanVar(value=True)
        self.skip_rated_flagged = tk.BooleanVar(value=True)
        self.skip_edited = tk.BooleanVar(value=True)

        # Internal state
        self.results: List[Dict[str, Any]] = []
        self._stop_requested = threading.Event()
        self._analysis_thread: Optional[threading.Thread] = None

        self.create_widgets()

    def show_beta_info(self):
        """Explain the 0-100 scores and how to read the table."""
        text = (
            "PRO-CULL assigns each photo a 0-100 technical score. Higher numbers "
            "generally mean sharper, cleaner, better-exposed files.\n\n"
            "Metric columns (0-100, higher is better):\n"
            "  Blur: 0 = very soft / motion-blurred, 100 = tack sharp\n"
            "  Comp: 0 = poor framing, 100 = strong rule-of-thirds / balance\n"
            "  Light: 0 = very difficult exposure, 100 = clean exposure & color\n"
            "  Noise: 0 = very noisy, 100 = very clean\n\n"
            "Overall Quality (Q column) is a weighted mix of these metrics.\n\n"
            "Rough guide for Quality (tweak to taste):\n"
            "  0-30: Often rejects (heavy blur or major issues)\n"
            "  30-65: On the fence - worth a closer look\n"
            "  65-80: Solid keepers for most jobs\n"
            "  80-100: Best-of-set candidates\n\n"
            "Chunking and pause settings help keep your machine responsive during large runs.\n"
            "Use 'Move rejects' with care; enable Dry Run to preview actions without moving files."
        )
        messagebox.showinfo("PRO-CULL BETA scoring", text)

    def create_widgets(self):
        # Directory selection
        dir_frame = ttk.Frame(self, padding="8")
        dir_frame.pack(fill=tk.X)
        ttk.Label(dir_frame, text="Image Directory:").pack(side=tk.LEFT)
        ttk.Entry(dir_frame, textvariable=self.image_dir, width=60).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(dir_frame, text="Browse", command=self.browse_directory).pack(side=tk.LEFT, padx=6)

        # Settings frame
        settings_frame = ttk.Frame(self, padding="8")
        settings_frame.pack(fill=tk.X)

        # Left column
        left_col = ttk.Frame(settings_frame)
        left_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(left_col, text="Blur threshold:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=2)
        ttk.Entry(left_col, textvariable=self.blur_threshold, width=8).grid(row=0, column=1, sticky=tk.W, padx=4)

        ttk.Label(left_col, text="Reject if quality <").grid(row=0, column=2, sticky=tk.W, padx=8)
        ttk.Entry(left_col, textvariable=self.reject_threshold, width=6).grid(row=0, column=3, sticky=tk.W, padx=4)

        ttk.Label(left_col, text="Review if quality <").grid(row=0, column=4, sticky=tk.W, padx=8)
        ttk.Entry(left_col, textvariable=self.review_threshold, width=6).grid(row=0, column=5, sticky=tk.W, padx=4)

        ttk.Checkbutton(left_col, text="Move rejects", variable=self.move_rejects).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=6)
        ttk.Label(left_col, text="Reject subdir:").grid(row=1, column=2, sticky=tk.W)
        ttk.Entry(left_col, textvariable=self.rejection_subdir, width=18).grid(row=1, column=3, sticky=tk.W)

        ttk.Checkbutton(left_col, text="Use RAW preview (if available)", variable=self.use_raw_preview).grid(row=1, column=4, columnspan=2, sticky=tk.W)

        # Additional settings controls
        ttk.Checkbutton(left_col, text="Use Blur metric", variable=self.use_blur).grid(row=2, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Use Composition metric", variable=self.use_composition).grid(row=2, column=2, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Use Lighting metric", variable=self.use_lighting).grid(row=2, column=4, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Use Noise metric", variable=self.use_noise).grid(row=3, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Write XMP sidecars", variable=self.write_xmp).grid(row=3, column=2, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Apply to Lightroom catalog", variable=self.apply_to_lightroom).grid(row=3, column=4, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Skip rated/flagged photos", variable=self.skip_rated_flagged).grid(row=4, column=0, columnspan=2, sticky=tk.W)
        ttk.Checkbutton(left_col, text="Skip edited photos", variable=self.skip_edited).grid(row=4, column=2, columnspan=2, sticky=tk.W)

        # Right column
        right_col = ttk.Frame(settings_frame)
        right_col.pack(side=tk.RIGHT, fill=tk.X)

        ttk.Label(right_col, text="Chunk size:").grid(row=0, column=0, sticky=tk.W, padx=4)
        ttk.Entry(right_col, textvariable=self.chunk_size, width=6).grid(row=0, column=1, sticky=tk.W, padx=4)

        ttk.Label(right_col, text="Pause between chunks (s):").grid(row=0, column=2, sticky=tk.W, padx=8)
        ttk.Entry(right_col, textvariable=self.pause_between_chunks, width=6).grid(row=0, column=3, sticky=tk.W, padx=4)

        ttk.Label(right_col, text="Max images (0 = all):").grid(row=1, column=0, sticky=tk.W, padx=4, pady=6)
        ttk.Entry(right_col, textvariable=self.max_images, width=6).grid(row=1, column=1, sticky=tk.W, padx=4)

        ttk.Checkbutton(right_col, text="Dry run (no moves)", variable=self.dry_run).grid(row=1, column=2, columnspan=2, sticky=tk.W)

        ttk.Label(settings_frame, text="BETA: Scoring weights are experimental.").pack(side=tk.BOTTOM, anchor=tk.W, padx=8, pady=4)

        # Controls
        control_frame = ttk.Frame(self, padding="8")
        control_frame.pack(fill=tk.X)
        ttk.Button(control_frame, text="Start Analysis", command=self.start_analysis).pack(side=tk.LEFT)
        ttk.Button(control_frame, text="Stop", command=self.request_stop).pack(side=tk.LEFT, padx=6)
        ttk.Button(control_frame, text="BETA info", command=self.show_beta_info).pack(side=tk.RIGHT)

        self.progress_label = ttk.Label(control_frame, text="Idle")
        self.progress_label.pack(side=tk.LEFT, padx=12)

        # Results table
        table_frame = ttk.Frame(self, padding="8")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("file", "quality", "blur", "comp", "light", "noise", "rating", "label", "collection")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=20)
        headings = {
            "file": "File",
            "quality": "Quality",
            "blur": "Blur",
            "comp": "Comp",
            "light": "Light",
            "noise": "Noise",
            "rating": "Rating",
            "label": "Label",
            "collection": "Collection",
        }
        for col, text in headings.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=120 if col != "file" else 380, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # EXIF/details pane
        detail_frame = ttk.Frame(self, padding="8")
        detail_frame.pack(fill=tk.X)
        ttk.Label(detail_frame, text="Selected EXIF / details:").pack(anchor=tk.W)
        self.detail_text = tk.Text(detail_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.detail_text.pack(fill=tk.X)

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.image_dir.set(directory)

    def start_analysis(self):
        image_dir = self.image_dir.get()
        if not image_dir:
            messagebox.showerror("Error", "Please select an image directory.")
            return

        if self._analysis_thread and self._analysis_thread.is_alive():
            messagebox.showinfo("Analysis running", "Analysis is already running.")
            return

        # Reset stop flag and results
        self._stop_requested.clear()
        self.results = []
        self.clear_table()
        self._analysis_thread = threading.Thread(target=self.run_analysis, daemon=True)
        self._analysis_thread.start()

    def request_stop(self):
        self._stop_requested.set()
        self.update_progress("Stop requested; finishing current image...")

    def run_analysis(self):
        start_time = time.time()
        image_dir = self.image_dir.get()
        blur_threshold = float(self.blur_threshold.get())
        move_rejects = bool(self.move_rejects.get())
        reject_subdir = self.rejection_subdir.get()
        reject_cut = float(self.reject_threshold.get())
        review_cut = float(self.review_threshold.get())
        use_raw = bool(self.use_raw_preview.get()) and RAW_PREVIEW_AVAILABLE
        chunk_size = max(1, int(self.chunk_size.get()))
        pause_secs = max(0.0, float(self.pause_between_chunks.get()))
        max_images = int(self.max_images.get())
        dry_run = bool(self.dry_run.get())

        log_event(f"run_start dir={image_dir} blur_threshold={blur_threshold} reject<{reject_cut} review<{review_cut} move_rejects={move_rejects} use_raw={use_raw} chunk={chunk_size} pause={pause_secs} dry_run={dry_run}")

        try:
            images = list(find_images([image_dir]))
            total = len(images)
            if max_images > 0:
                images = images[:max_images]
                total = len(images)
            if total == 0:
                self.update_progress("No images found.")
                return

            self.update_progress(f"Discovered {total} images")
            processed = 0
            moved_count = 0
            error_count = 0
            failures: List[str] = []

            # For ETA: track average per-image time (exponential moving average)
            avg_time = None
            alpha = 0.15

            for chunk_start in range(0, total, chunk_size):
                if self._stop_requested.is_set():
                    break
                chunk = images[chunk_start : min(chunk_start + chunk_size, total)]
                for idx, image_path in enumerate(chunk, start=chunk_start + 1):
                    if self._stop_requested.is_set():
                        break
                    self.update_progress(f"[{idx}/{total}] {pathlib.Path(image_path).name}")
                    t0 = time.time()
                    try:
                        # Read image (RAW-aware if requested)
                        if use_raw:
                            try:
                                img = read_image_or_raw(str(image_path))
                            except Exception:
                                img = cv2.imread(str(image_path))
                        else:
                            img = cv2.imread(str(image_path))

                        if img is None:
                            self.update_progress(f"Failed to read image: {image_path}")
                            failures.append(f"read_fail:{image_path}")
                            error_count += 1
                            continue

                        processed_image = fix_image_size(img.copy())
                        blur_map, lap_var, blurry_flag = estimate_blur(processed_image, threshold=blur_threshold)

                        exif = extract_exif(str(image_path))
                        blur_score = score_blur(lap_var, exif.get("shutter"), exif.get("focal_length"))
                        comp_score = evaluate_composition(str(image_path))
                        light_dict = evaluate_lighting(str(image_path))
                        light_score = lighting_to_scalar(light_dict) if light_dict else None
                        iso = exif.get("iso") or 100.0
                        noise_score = estimate_noise_score(str(image_path), iso=iso)
                        exposure_score = light_score

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
                        enabled_metrics = []
                        if self.use_blur.get():
                            enabled_metrics.append("blur")
                        if self.use_composition.get():
                            enabled_metrics.append("composition")
                        if self.use_lighting.get():
                            enabled_metrics.append("lighting")
                            enabled_metrics.append("exposure")
                        if self.use_noise.get():
                            enabled_metrics.append("noise")

                        q_score = quality_score(metric_scores, metric_weights, enabled_metrics)
                        rating = rating_for_score(q_score, blurry_flag)
                        label = label_for_score(q_score, blurry_flag)
                        collection = collection_for_score(q_score, blurry_flag)

                        row = {
                            "path": str(image_path),
                            "quality": q_score,
                            "blur": blur_score,
                            "comp": comp_score,
                            "light": light_score,
                            "noise": noise_score,
                            "rating": rating,
                            "label": label,
                            "collection": collection,
                            "exif": exif,
                            "exposure": exposure_score,
                            "blurry": bool(blurry_flag),
                        }
                        self.results.append(row)
                        self.insert_row(row)

                        # Move rejects if configured
                        if move_rejects and (q_score < reject_cut or blurry_flag):
                            try:
                                moved = self.safe_move(image_path, reject_subdir, dry_run=dry_run)
                                if moved:
                                    moved_count += 1
                            except Exception as e:
                                log_event(f"move_error {image_path} {e}")
                                failures.append(f"move_error:{image_path}")
                                error_count += 1

                        processed += 1

                    except Exception as e:
                        log_event(f"process_error {image_path} {e}")
                        failures.append(f"process_error:{image_path}")
                        error_count += 1

                    # timing and ETA
                    t1 = time.time()
                    elapsed = t1 - t0
                    if avg_time is None:
                        avg_time = elapsed
                    else:
                        avg_time = (1 - alpha) * avg_time + alpha * elapsed
                    remaining = total - idx
                    eta = remaining * (avg_time or 0)
                    eta_str = self._format_seconds(eta)
                    self.update_progress(f"[{idx}/{total}] {pathlib.Path(image_path).name} | ETA: {eta_str}")

                # Pause between chunks to let system breathe
                if pause_secs > 0 and (chunk_start + chunk_size) < total and not self._stop_requested.is_set():
                    self.update_progress(f"Pausing {pause_secs:.1f}s between chunks...")
                    time.sleep(pause_secs)

            elapsed_total = time.time() - start_time
            summary = {
                "processed": processed,
                "moved": moved_count,
                "errors": error_count,
                "failures_sample": failures[:10],
                "elapsed_seconds": round(elapsed_total, 2),
            }
            log_event(f"run_complete dir={image_dir} processed={processed} moved={moved_count} errors={error_count} elapsed={elapsed_total:.2f}s")
            self.update_progress("Analysis complete (BETA scoring).")
            self._show_run_summary(summary)

        except Exception as e:
            log_event(f"run_error dir={image_dir} error={e}")
            self.update_progress(f"An error occurred: {e}")
            messagebox.showerror("Analysis error", f"An unexpected error occurred:\n{e}")

    def safe_move(self, image_path: str, target_subdir: str, dry_run: bool = False) -> bool:
        """
        Move image to target_subdir next to original. If destination exists, append a numeric suffix.
        Returns True if moved (or would be moved in dry_run), False otherwise.
        """
        src = pathlib.Path(image_path)
        original_dir = src.parent
        target_dir = original_dir / target_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / src.name

        # If destination exists, append suffix before extension
        if dest.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while True:
                candidate = target_dir / f"{stem}_{counter}{suffix}"
                if not candidate.exists():
                    dest = candidate
                    break
                counter += 1

        if dry_run:
            log_event(f"dry_move: {src} -> {dest}")
            return True

        # Attempt atomic move
        try:
            shutil.move(str(src), str(dest))
            log_event(f"MOVED '{src}' -> '{dest}'")
            return True
        except Exception as e:
            log_event(f"move_failed {src} -> {dest} : {e}")
            raise

    def _show_run_summary(self, summary: Dict[str, Any]):
        processed = summary.get("processed", 0)
        moved = summary.get("moved", 0)
        errors = summary.get("errors", 0)
        elapsed = summary.get("elapsed_seconds", 0.0)
        failures = summary.get("failures_sample", [])

        msg = (
            f"Analysis complete.\n\n"
            f"Processed: {processed}\n"
            f"Moved (rejects): {moved}\n"
            f"Errors: {errors}\n"
            f"Elapsed: {self._format_seconds(elapsed)}\n\n"
        )
        if failures:
            msg += "Sample failures:\n" + "\n".join(failures) + "\n\n"
        msg += "See pro-cull-gui.log for full details."

        # Show summary in a non-blocking dialog
        messagebox.showinfo("Run Summary", msg)

    def clear_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

    def insert_row(self, row: Dict[str, Any]):
        try:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    pathlib.Path(row["path"]).name,
                    f"{row['quality']:.1f}",
                    f"{row['blur']:.1f}",
                    f"{(row['comp'] or 0):.1f}",
                    f"{(row['light'] or 0):.1f}",
                    f"{(row['noise'] or 0):.1f}",
                    row["rating"],
                    row["label"],
                    row["collection"],
                ),
                tags=(row["path"],),
            )
        except Exception:
            # Defensive: ignore UI insertion errors but log them
            log_event(f"ui_insert_error {row.get('path')}")

    def on_row_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        path_tag = self.tree.item(sel[0])["tags"][0]
        row = next((r for r in self.results if r["path"] == path_tag), None)
        if not row:
            return
        exif = row.get("exif", {})
        detail_lines = [
            f"Path: {row['path']}",
            f"Quality: {row['quality']:.1f} | Blur: {row['blur']:.1f} | Comp: {(row['comp'] or 0):.1f} | Light: {(row['light'] or 0):.1f} | Noise: {(row['noise'] or 0):.1f}",
            f"Rating: {row['rating']} | Label: {row['label']} | Collection: {row['collection']}",
            f"Shutter: {exif.get('shutter')}  Aperture: {exif.get('aperture')}  ISO: {exif.get('iso')}  Focal: {exif.get('focal_length')}",
            f"Camera: {exif.get('camera_model')}  Lens: {exif.get('lens_model')}",
            f"DateTime: {exif.get('datetime')}",
        ]
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(tk.END, "\n".join(detail_lines))
        self.detail_text.config(state=tk.DISABLED)

    def update_progress(self, message: str):
        def updater():
            self.progress_label.config(text=message)
        self.after(0, updater)

    @staticmethod
    def _format_seconds(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        m, s = divmod(int(seconds), 60)
        if m < 60:
            return f"{m}m{s:02d}s"
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m"

if __name__ == "__main__":
    app = BlurDetectorGUI()
    app.mainloop()