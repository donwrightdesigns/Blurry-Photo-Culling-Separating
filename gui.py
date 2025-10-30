
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import queue
import json
import pathlib
import os
from process import find_images, estimate_blur, fix_image_size
import cv2
import shutil

class BlurDetectorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Blur Detector")
        self.geometry("800x600")

        self.image_dir = tk.StringVar()
        self.threshold = tk.DoubleVar(value=100.0)
        self.move_blurry = tk.BooleanVar()
        self.blurry_subdir = tk.StringVar(value="blurry_images")
        
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
        ttk.Label(settings_frame, text="Threshold:").pack(side=tk.LEFT)
        ttk.Entry(settings_frame, textvariable=self.threshold, width=10).pack(side=tk.LEFT)
        ttk.Checkbutton(settings_frame, text="Move Blurry Images", variable=self.move_blurry).pack(side=tk.LEFT, padx=10)
        ttk.Label(settings_frame, text="Blurry Subdir:").pack(side=tk.LEFT)
        ttk.Entry(settings_frame, textvariable=self.blurry_subdir, width=20).pack(side=tk.LEFT)

        # Frame for controls
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X)
        ttk.Button(control_frame, text="Start Analysis", command=self.start_analysis).pack(side=tk.LEFT)

        # Frame for results
        results_frame = ttk.Frame(self, padding="10")
        results_frame.pack(fill=tk.BOTH, expand=True)
        self.results_text = tk.Text(results_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.results_text.pack(fill=tk.BOTH, expand=True)

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.image_dir.set(directory)

    def start_analysis(self):
        image_dir = self.image_dir.get()
        if not image_dir:
            messagebox.showerror("Error", "Please select an image directory.")
            return

        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, "Starting analysis...\n")
        self.results_text.config(state=tk.DISABLED)

        self.analysis_thread = threading.Thread(target=self.run_analysis, daemon=True)
        self.analysis_thread.start()

    def run_analysis(self):
        # This will run in a separate thread to keep the GUI responsive
        image_dir = self.image_dir.get()
        threshold = self.threshold.get()
        move_blurry = self.move_blurry.get()
        blurry_subdir = self.blurry_subdir.get()

        try:
            for image_path in find_images([image_dir]):
                image = cv2.imread(str(image_path))
                if image is None:
                    self.update_results(f"Failed to read image: {image_path}\n")
                    continue

                processed_image = fix_image_size(image.copy())
                blur_map, score, blurry = estimate_blur(processed_image, threshold=threshold)
                
                result_str = f"Image: {image_path.name}, Score: {score:.2f}, Blurry: {blurry}\n"
                self.update_results(result_str)

                if move_blurry and blurry:
                    self.move_image(image_path, blurry_subdir)
            
            self.update_results("Analysis complete.\n")

        except Exception as e:
            self.update_results(f"An error occurred: {e}\n")

    def move_image(self, image_path, blurry_subdir):
        try:
            original_image_dir = image_path.parent
            target_blurry_dir = original_image_dir / blurry_subdir
            target_blurry_dir.mkdir(parents=True, exist_ok=True)
            destination_path = target_blurry_dir / image_path.name

            if destination_path.exists():
                self.update_results(f"File '{destination_path}' already exists. Skipping move.\n")
            elif image_path.exists():
                shutil.move(str(image_path), str(destination_path))
                self.update_results(f"MOVED blurry image: '{image_path}' -> '{destination_path}'\n")
            else:
                self.update_results(f"Source image '{image_path}' not found for moving.\n")

        except Exception as e:
            self.update_results(f"Error moving blurry image '{image_path}': {e}\n")

    def update_results(self, message):
        def updater():
            self.results_text.config(state=tk.NORMAL)
            self.results_text.insert(tk.END, message)
            self.results_text.see(tk.END)
            self.results_text.config(state=tk.DISABLED)
        self.after(0, updater)

if __name__ == "__main__":
    app = BlurDetectorGUI()
    app.mainloop()

