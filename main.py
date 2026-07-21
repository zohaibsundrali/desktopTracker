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

# Check if Supabase credentials are set
if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
    _fatal(
        "Configuration error",
        "Supabase credentials not found.\n\n"
        "The application could not read SUPABASE_URL / SUPABASE_KEY.\n"
        "Please contact your administrator.",
    )
    sys.exit(1)


def main():
    """Main application entry point"""
    try:
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


if __name__ == "__main__":
    main()
