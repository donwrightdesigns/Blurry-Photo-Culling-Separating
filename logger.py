import logging
import logging.handlers
import os
from tkinter import scrolledtext
import tkinter as tk

# --- Constants ---
LOG_FILENAME = "pro-cull.log"
MAX_LOG_SIZE_MB = 5
BACKUP_COUNT = 3

# --- GUI Handler ---
class ScrolledTextHandler(logging.Handler):
    """A logging handler that redirects logs to a tkinter ScrolledText widget."""
    def __init__(self, text_widget: scrolledtext.ScrolledText):
        super().__init__()
        self.text_widget = text_widget
        self.text_widget.config(state=tk.DISABLED)

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, msg + '\\n')
        self.text_widget.see(tk.END)
        self.text_widget.config(state=tk.DISABLED)

# --- Configuration ---
def setup_logging(gui_log_widget: scrolledtext.ScrolledText = None, level=logging.INFO):
    """
    Configure root logger for file and optional GUI output.
    - level: The minimum level of messages to log.
    - gui_log_widget: A tkinter ScrolledText widget for live log display.
    """
    log_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(module)-15s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Root logger
    logger = logging.getLogger()
    logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates on re-configuration
    if logger.hasHandlers():
        logger.handlers.clear()

    # File handler (rotating)
    log_path = os.path.join(os.getcwd(), LOG_FILENAME)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, 
        maxBytes=MAX_LOG_SIZE_MB * 1024 * 1024, 
        backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # GUI handler (if widget is provided)
    if gui_log_widget:
        gui_handler = ScrolledTextHandler(gui_log_widget)
        gui_handler.setFormatter(log_format)
        gui_handler.setLevel(logging.INFO) # Only show INFO and above in GUI
        logger.addHandler(gui_handler)

    logging.info("--- Logging initialized ---")

# --- Example Usage ---
# if __name__ == '__main__':
#     # This demonstrates how to use it in the GUI
#     root = tk.Tk()
#     root.title("Log Test")
#     log_widget = scrolledtext.ScrolledText(root, width=80, height=20)
#     log_widget.pack()
#     
#     setup_logging(gui_log_widget=log_widget, level=logging.DEBUG)
#     
#     logging.debug("This is a debug message.")
#     logging.info("This is an info message.")
#     logging.warning("This is a warning message.")
#     logging.error("This is an error message.")
#     
#     root.mainloop()
