"""Application entry point and startup error boundary."""
import argparse
import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from memora.config import load_settings
from memora.database import Repository
from memora.errors import MemoraError
from memora.gui.main_window import MainWindow
from memora.logging_utils import configure_logging


def main():
    parser = argparse.ArgumentParser(description="Memora: your private local document library")
    parser.add_argument("--data-dir", type=Path, help="Use a different application data folder")
    args = parser.parse_args()
    try:
        root = tk.Tk()
    except tk.TclError:
        parser.exit(1, "Memora requires a working Tkinter installation and desktop session.\n"
                       "Install Python with Tcl/Tk support (or your system's python3-tk package).\n")
    root.withdraw()
    repository = handler = None
    try:
        settings = load_settings(args.data_dir)
        handler = configure_logging(settings.data_dir)
        repository = Repository(settings.database_path)
        MainWindow(root, repository, settings)
    except Exception as exc:
        logging.getLogger("memora").error("Startup failed (%s).", type(exc).__name__)
        detail = str(exc) if isinstance(exc, MemoraError) else (
            "Cannot open Memora's data. Check that the data folder is writable and has free space.")
        messagebox.showerror("Memora could not start",
            detail + "\n\n"
            "You can select another folder with: python main.py --data-dir PATH", parent=root)
        if repository:
            repository.close()
        root.destroy()
    else:
        root.deiconify()
        root.mainloop()
    finally:
        if handler:
            logging.getLogger("memora").removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    main()
