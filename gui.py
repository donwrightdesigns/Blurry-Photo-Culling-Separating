
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import json
import pathlib
import os
import cv2
import shutil

from blur_detection import estimate_blur, fix_image_size
from process import (
    find_images,
    score_blur,
    lighting_to_scalar,
    quality_score,
    rating_for_score,
    label_for_score,
    collection_for_score,
)
from metrics import (
    evaluate_composition,
    evaluate_lighting,
    estimate_noise_score,
    extract_exif,
)

class BlurDetectorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PRECURSOR Technical Culling")
        self.geometry("1100x720")

        self.image_dir = tk.StringVar()
        self.blur_threshold = tk.DoubleVar(value=100.0)
        self.reject_threshold = tk.DoubleVar(value=30.0)
        self.review_threshold = tk.DoubleVar(value=65.0)
        self.move_rejects = tk.BooleanVar()
        self.rejection_subdir = tk.StringVar(value="Blurry-Images")

        self.results = []

        self.create_widgets()

    def create_widgets(self):
        # Frame for directory selection
        dir_frame = ttk.Frame(self, padding="10")
        dir_frame.pack(fill=tk.X)
        ttk.Label(dir_frame, text="Image Directory:").pack(side=tk.LEFT)
        ttk.Entry(dir_frame, textvariable=self.image_dir, width=50).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(dir_frame, text="Browse", command=self.browse_directory).pack(side=tk.LEFT)

        # Frame for settings
        settings_frame = ttk.Frame(self, padding="10")
        settings_frame.pack(fill=tk.X)
        ttk.Label(settings_frame, text="Blur threshold:").pack(side=tk.LEFT)
        ttk.Entry(settings_frame, textvariable=self.blur_threshold, width=8).pack(side=tk.LEFT)
        ttk.Label(settings_frame, text="Reject if quality <").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(settings_frame, textvariable=self.reject_threshold, width=6).pack(side=tk.LEFT)
        ttk.Label(settings_frame, text="Review if quality <").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(settings_frame, textvariable=self.review_threshold, width=6).pack(side=tk.LEFT)
        ttk.Checkbutton(settings_frame, text="Move rejects", variable=self.move_rejects).pack(side=tk.LEFT, padx=10)
        ttk.Label(settings_frame, text="Reject subdir:").pack(side=tk.LEFT)
        ttk.Entry(settings_frame, textvariable=self.rejection_subdir, width=18).pack(side=tk.LEFT)

        # Frame for controls
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)
        ttk.Button(control_frame, text="Start Analysis", command=self.start_analysis).pack(side=tk.LEFT)
        self.progress_label = ttk.Label(control_frame, text="Idle")
        self.progress_label.pack(side=tk.LEFT, padx=10)

        # Frame for results table
        table_frame = ttk.Frame(self, padding="10")
        table_frame.pack(fill=tk.BOTH, expand=True)
        columns = (
            "file",
            "quality",
            "blur",
            "comp",
            "light",
            "noise",
            "rating",
            "label",
            "collection",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=18)
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
            self.tree.column(col, width=110 if col != "file" else 280, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Frame for EXIF/details
        detail_frame = ttk.Frame(self, padding="10")
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


        self.analysis_thread = threading.Thread(target=self.run_analysis, daemon=True)
        self.analysis_thread.start()

    def run_analysis(self):
        # This will run in a separate thread to keep the GUI responsive
        image_dir = self.image_dir.get()
        blur_threshold = self.blur_threshold.get()
        move_rejects = self.move_rejects.get()
        reject_subdir = self.rejection_subdir.get()
        reject_cut = self.reject_threshold.get()
        review_cut = self.review_threshold.get()

        try:
            images = list(find_images([image_dir]))
            total = len(images)
            self.update_progress(f"Discovered {total} images")
            self.results = []
            self.clear_table()

            for idx, image_path in enumerate(images, start=1):
                self.update_progress(f"[{idx}/{total}] {image_path.name}")
                image = cv2.imread(str(image_path))
                if image is None:
                    self.update_progress(f"Failed to read image: {image_path}")
                    continue

                processed_image = fix_image_size(image.copy())
                blur_map, lap_var, blurry_flag = estimate_blur(processed_image, threshold=blur_threshold)

                exif = extract_exif(str(image_path))
                blur_score = score_blur(lap_var, exif.get("shutter"), exif.get("focal_length"))
                comp_score = evaluate_composition(str(image_path))
                light_dict = evaluate_lighting(str(image_path))
                light_score = lighting_to_scalar(light_dict)
                iso = exif.get("iso") or 100.0
                noise_score = estimate_noise_score(str(image_path), iso=iso)
                # Exposure proxy reuse lighting mid-score
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
                enabled_metrics = ["blur", "composition", "lighting", "noise", "exposure"]
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

                if move_rejects and (q_score < reject_cut or blurry_flag):
                    self.move_image(image_path, reject_subdir)

            self.update_progress("Analysis complete.")

        except Exception as e:
            self.update_progress(f"An error occurred: {e}")

    def move_image(self, image_path, target_subdir):
        try:
            original_image_dir = image_path.parent
            target_blurry_dir = original_image_dir / target_subdir
            target_blurry_dir.mkdir(parents=True, exist_ok=True)
            destination_path = target_blurry_dir / image_path.name

            if destination_path.exists():
                self.update_progress(f"File '{destination_path}' exists. Skipping move.")
            elif image_path.exists():
                shutil.move(str(image_path), str(destination_path))
                self.update_progress(f"MOVED '{image_path.name}' -> '{destination_path}'")
            else:
                self.update_progress(f"Source image '{image_path}' not found for moving.")

        except Exception as e:
            self.update_progress(f"Error moving image '{image_path}': {e}")

    def clear_table(self):
        for r in self.tree.get_children():
            self.tree.delete(r)

    def insert_row(self, row):
        self.tree.insert(
            "",
            tk.END,
            values=(
                pathlib.Path(row["path"]).name,
                f"{row['quality']:.1f}",
                f"{row['blur']:.1f}",
                f"{row['comp']:.1f}",
                f"{row['light']:.1f}",
                f"{row['noise']:.1f}",
                row["rating"],
                row["label"],
                row["collection"],
            ),
            tags=(row["path"],),
        )

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
            f"Quality: {row['quality']:.1f} | Blur: {row['blur']:.1f} | Comp: {row['comp']:.1f} | Light: {row['light']:.1f} | Noise: {row['noise']:.1f}",
            f"Rating: {row['rating']} | Label: {row['label']} | Collection: {row['collection']}",
            f"Shutter: {exif.get('shutter')}  Aperture: {exif.get('aperture')}  ISO: {exif.get('iso')}  Focal: {exif.get('focal_length')}",
            f"Camera: {exif.get('camera_model')}  Lens: {exif.get('lens_model')}",
            f"DateTime: {exif.get('datetime')}",
        ]
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete(1.0, tk.END)
        self.detail_text.insert(tk.END, "\n".join(detail_lines))
        self.detail_text.config(state=tk.DISABLED)

    def update_progress(self, message):
        def updater():
            self.progress_label.config(text=message)
        self.after(0, updater)

if __name__ == "__main__":
    app = BlurDetectorGUI()
    app.mainloop()

