#!/usr/bin/env python3
"""
selftest.py - readiness & capability check for Developer Tracker.

Run this on the machine where the tracker will actually run (Windows) to
confirm every feature has what it needs. It does NOT start a full tracking
session - it checks dependencies, the Supabase connection, and the low-level
capture capabilities that Mouse / Keyboard / Screenshot / App-tracking rely on.

    python selftest.py
"""
import sys
import platform

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
_ICON = {PASS: "[ OK ]", FAIL: "[FAIL]", WARN: "[WARN]"}
results = []


def record(name, status, detail=""):
    results.append((name, status, detail))
    print(f"{_ICON[status]}  {name:34} {detail}")


print("=" * 64)
print(" Developer Tracker - Self Test")
print("=" * 64)

# 1) Python version
v = sys.version_info
record("Python >= 3.10", PASS if v >= (3, 10) else WARN, f"{v.major}.{v.minor}.{v.micro}")

# 2) Platform (full capture is Windows-only)
osname = platform.system()
record("Platform", PASS if osname == "Windows" else WARN,
       osname + ("" if osname == "Windows" else " - capture is Windows-only"))

# 3) Core dependencies
for d in ["customtkinter", "supabase", "pyautogui", "pynput",
          "psutil", "pandas", "numpy", "PIL", "dotenv"]:
    try:
        __import__(d)
        record(f"import {d}", PASS)
    except Exception as e:
        record(f"import {d}", FAIL, str(e)[:44])

# 3b) Windows-only input/window deps
if osname == "Windows":
    for d in ["win32gui", "win32process"]:
        try:
            __import__(d)
            record(f"import {d}", PASS)
        except Exception:
            record(f"import {d}", FAIL, "pip install pywin32")

# 4) .env / config
try:
    from config import config
    url_ok = bool(config.SUPABASE_URL) and "supabase.co" in config.SUPABASE_URL
    key_ok = bool(config.SUPABASE_KEY) and len(config.SUPABASE_KEY) > 20
    record(".env SUPABASE_URL", PASS if url_ok else FAIL,
           "" if url_ok else "missing/invalid - copy .env.example to .env")
    record(".env SUPABASE_KEY", PASS if key_ok else FAIL,
           "" if key_ok else "missing/invalid")
except Exception as e:
    record("load config (.env)", FAIL, str(e)[:44])

# 5) Supabase connection (read-only)
try:
    from supabase import create_client
    from config import config
    sb = create_client(config.SUPABASE_URL.strip(), config.SUPABASE_KEY.strip())
    sb.table("developers").select("id").limit(1).execute()
    record("Supabase connection", PASS, "reachable, query OK")
except Exception as e:
    record("Supabase connection", FAIL, str(e)[:52])

# 6) Feature capabilities - low-level probes (no tracker internals)
#    Screenshot
try:
    import pyautogui
    w, h = pyautogui.screenshot().size
    record("Screenshot capture", PASS if w > 0 and h > 0 else FAIL, f"{w}x{h}")
except Exception as e:
    record("Screenshot capture", FAIL, str(e)[:44])

#    Mouse position read
try:
    import pyautogui
    x, y = pyautogui.position()
    record("Mouse position read", PASS, f"cursor at ({x},{y})")
except Exception as e:
    record("Mouse position read", FAIL, str(e)[:44])

#    Mouse event listener
try:
    from pynput import mouse
    ml = mouse.Listener(on_move=lambda *a: None)
    ml.start(); ml.stop()
    record("Mouse event listener", PASS)
except Exception as e:
    record("Mouse event listener", FAIL, str(e)[:44])

#    Keyboard listener
try:
    from pynput import keyboard
    kl = keyboard.Listener(on_press=lambda *a: None)
    kl.start(); kl.stop()
    record("Keyboard listener", PASS)
except Exception as e:
    record("Keyboard listener", FAIL, str(e)[:44])

#    App / window detection
try:
    from app_monitor import get_foreground_app, get_foreground_title
    if osname == "Windows":
        app = get_foreground_app()
        title = get_foreground_title()
        record("App/window detection", PASS if app else WARN,
               f"active: {app} | {title[:28]}")
    else:
        record("App/window detection", WARN, "Windows-only")
except Exception as e:
    record("App/window detection", FAIL, str(e)[:44])

# Summary
print("=" * 64)
npass = sum(1 for _, s, _ in results if s == PASS)
nfail = sum(1 for _, s, _ in results if s == FAIL)
nwarn = sum(1 for _, s, _ in results if s == WARN)
print(f" RESULT: {npass} passed, {nfail} failed, {nwarn} warnings")
if nfail == 0:
    print(" All critical checks passed - features are ready to capture.")
else:
    print(" Some checks FAILED - fix the [FAIL] items above, then re-run.")
print("=" * 64)
sys.exit(1 if nfail else 0)
