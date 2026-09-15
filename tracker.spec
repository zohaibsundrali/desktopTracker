# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build spec for Developer Tracker.
#   Build with:  pyinstaller tracker.spec --noconfirm
#
# Produces a windowed (no console) onedir app in dist\DeveloperTracker\.
import os
from PyInstaller.utils.hooks import collect_all

# ---- Collect data files / hidden imports for tricky packages -----------------
datas, binaries, hiddenimports = [], [], []
for pkg in ("customtkinter", "supabase", "pynput", "pyautogui", "PIL"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Extra hidden imports some deps pull in dynamically.
hiddenimports += [
    "diagnostics",
    "app_version",
    "instance_lock",
    "desktop_updates",
    "desktop_support",
    "windows_session_guard",
    "win32ts",
    "public_config",
    "session_outbox",
    "screenshot_outbox",
    "screenshot_upload",
    "screenshot_limits",
    "tracking_work",
    "tracker_presence",
    "break_tracker",
    "idle_reminder",
    "activity_outbox",
    "input_outbox",
    "input_upload",
    "activity_upload",
    "screenshot_policy",
    "sqlite3",
    "_sqlite3",
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "PIL._tkinter_finder",
    # pywin32 — required for foreground app/window + process detection.
    "win32gui",
    "win32process",
    "win32api",
    "win32con",
    "pywintypes",
    "pythoncom",
]

# Collect pywin32 (Windows only) so app/website tracking works in the frozen app.
try:
    d, b, h = collect_all("win32")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

# uiautomation is Windows-only (browser address-bar reading). Optional.
try:
    d, b, h = collect_all("uiautomation")
    datas += d
    binaries += b
    hiddenimports += h
except Exception:
    pass

# Only the validated, allowlisted configuration enters a distributable build.
public_env = os.path.join("build", "public-config", ".env")
if not os.path.isfile(public_env):
    raise SystemExit("Run python scripts/prepare_public_config.py before packaging.")
from dotenv import dotenv_values
from public_config import validate_public_config
public_values = dotenv_values(public_env, interpolate=False)
if set(public_values) - {"SUPABASE_URL", "SUPABASE_KEY", "SCREENSHOTS_ENABLED"}:
    raise SystemExit("Prepared config contains non-public fields. Re-run prepare_public_config.py.")
validate_public_config(public_values)
datas += [(public_env, ".")]

# ---- Optional app icon -------------------------------------------------------
icon_file = "app.ico" if os.path.exists("app.ico") else None

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeveloperTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # windowed app — no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DeveloperTracker",
)
