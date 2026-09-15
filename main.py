# main.py - entry point (works both as a script and as a PyInstaller .exe)
import sys
import os
import traceback
from dotenv import load_dotenv


def _fatal(title: str, message: str) -> None:
    """Show an error the user can actually see.

    When packaged as a windowed .exe there is no console, so print() is
    invisible. Fall back to a native message box; if even that fails, print.
    """
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        print(f"{title}: {message}")


def _load_env() -> None:
    """Load .env from every location that makes sense.

    - Running as a script: the folder next to this file.
    - Running as a PyInstaller bundle: the temp extract dir (sys._MEIPASS)
      where the bundled .env lands, AND the folder next to the .exe so an
      admin can override config without rebuilding.
    """
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS", ""), ".env"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), ".env"))
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    candidates.append(".env")  # current working dir, last

    loaded = False
    for path in candidates:
        if path and os.path.exists(path):
            load_dotenv(path, override=False)
            loaded = True
    if not loaded:
        load_dotenv()  # default search as a final fallback


_load_env()


def main():
    """Main application entry point"""
    if len(sys.argv) == 3 and sys.argv[1] == "--diagnostics":
        from diagnostics import write_report
        try:
            return write_report(sys.argv[2])
        except OSError:
            _fatal("Diagnostics", "The report could not be saved. Choose a writable location.")
            return 1
    from public_config import PublicConfigError, validate_public_config
    try:
        validate_public_config(os.environ)
    except PublicConfigError as exc:
        _fatal("Configuration error", str(exc) + "\n\nPlease contact your administrator.")
        return 1
    from config import user_data_dir
    from instance_lock import InstanceLock
    instance = None
    try:
        instance = InstanceLock(user_data_dir())
        if not instance.acquire():
            _fatal("DevTrack is already open", "Use the existing DevTrack window. Only one tracker can run for this Windows user.")
            return 1
        from gui_login import main as gui_main
        gui_main()
    except ImportError as e:
        traceback.print_exc()
        _fatal("Startup error", f"A required component failed to load:\n\n{e}")
        sys.exit(1)
    except Exception as e:
        traceback.print_exc()
        _fatal("Unexpected error", f"The application could not start:\n\n{e}")
        sys.exit(1)

    finally:
        if instance:
            instance.release()


if __name__ == "__main__":
    sys.exit(main())
