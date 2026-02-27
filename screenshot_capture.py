"""
screenshot_capture.py
─────────────────────
Captures screenshots at random intervals, uploads them directly to
Supabase Storage (in-memory only — nothing written to disk), and
inserts metadata into a Supabase table.

Requirements:
    pip install pyautogui pillow supabase python-dotenv pandas

.env variables:
    SUPABASE_URL      – your project URL
    SUPABASE_KEY      – service-role or anon key
    DEVELOPER_ID      – identifier stored with each upload
    DEVELOPER_EMAIL   – email stored with each upload  (optional)

Supabase setup:
    • Storage bucket  : screenshots_bucket  (public or private)
    • Table           : screenshots
      Columns: id (uuid pk), user_id (text), email (text),
               filename (text), storage_path (text), public_url (text),
               width (int4), height (int4), size_kb (float8),
               timestamp (timestamptz), app_active (text)
"""

from __future__ import annotations

import io
import json
import os
import queue
import random
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional

import pyautogui
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

import tkinter as tk
from tkinter import ttk

load_dotenv()

# ── Environment ───────────────────────────────────────────────────────────────

SUPABASE_URL    = os.getenv("SUPABASE_URL")
SUPABASE_KEY    = os.getenv("SUPABASE_KEY")
DEVELOPER_ID    = os.getenv("DEVELOPER_ID", "unknown")
DEVELOPER_EMAIL = os.getenv("DEVELOPER_EMAIL", "unknown")

STORAGE_BUCKET = "screenshots"
METADATA_TABLE = "screenshots"

# ─────────────────────────────────────────────────────────────────────────────


def _supabase_client():
    """Return a Supabase client or None if credentials are missing."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️  SUPABASE_URL / SUPABASE_KEY not set — upload skipped.")
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ScreenshotInfo:
    timestamp:  str
    filename:   str
    width:      int
    height:     int
    size_kb:    float
    public_url: Optional[str] = None
    app_active: Optional[str] = None


# ── Popup notification ────────────────────────────────────────────────────────

class NotificationPopup:
    """
    Lightweight bottom-right toast that says "Screenshot captured successfully".
    Runs in its own daemon thread so it never blocks capture.
    """

    def __init__(self):
        self._q:      queue.Queue = queue.Queue()
        self._root:   Optional[tk.Tk] = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass

    def notify(self):
        if self._running:
            self._q.put_nowait("show")

    # ── internal ──────────────────────────────────────────────────────────────

    def _loop(self):
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            while self._running:
                self._drain()
                try:
                    self._root.update()
                except Exception:
                    break
                time.sleep(0.05)
        except Exception as exc:
            print(f"⚠️  Notification thread error: {exc}")

    def _drain(self):
        try:
            while True:
                self._q.get_nowait()
                self._show_toast()
        except queue.Empty:
            pass

    def _show_toast(self):
        try:
            W, H = 300, 90
            sw = self._root.winfo_screenwidth()
            sh = self._root.winfo_screenheight()

            win = tk.Toplevel(self._root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.95)
            win.configure(bg="#1a1a1a")
            win.geometry(f"{W}x{H}+{sw - W - 20}+{sh - H - 60}")

            frm = tk.Frame(win, bg="#1a1a1a", padx=16, pady=12)
            frm.pack(fill=tk.BOTH, expand=True)

            tk.Label(frm, text="📸", font=("Arial", 22),
                     bg="#1a1a1a", fg="#4CAF50").pack(side=tk.LEFT, padx=(0, 12))

            txt = tk.Frame(frm, bg="#1a1a1a")
            txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tk.Label(txt, text="Screenshot",
                     font=("Arial", 13, "bold"), bg="#1a1a1a", fg="white"
                     ).pack(anchor=tk.W)
            tk.Label(txt, text="captured successfully",
                     font=("Arial", 10), bg="#1a1a1a", fg="#CCCCCC"
                     ).pack(anchor=tk.W)

            # Progress bar drains over 5 s
            bar_frame = tk.Frame(win, bg="#1a1a1a", height=3)
            bar_frame.pack(fill=tk.X, side=tk.BOTTOM)
            bar = ttk.Progressbar(bar_frame, mode="determinate",
                                  length=W, maximum=100, value=100)
            bar.pack(fill=tk.X)

            def _tick(v):
                if v > 0:
                    bar["value"] = v
                    bar.after(50, _tick, v - 2)

            _tick(100)
            win.after(5000, win.destroy)

        except Exception as exc:
            print(f"⚠️  Toast error: {exc}")


# ── Main capture engine ───────────────────────────────────────────────────────

class ScreenshotCapture:
    """
    Captures screenshots in-memory at random intervals and uploads
    directly to Supabase Storage + metadata table.
    """

    def __init__(
        self,
        interval_min: int = 1,
        interval_max: int = 60,
        compress:     bool = True,
        quality:      int  = 85,
        max_history:  int  = 200,
    ):
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.compress     = compress
        self.quality      = quality
        self.max_history  = max_history

        self._screenshots: List[ScreenshotInfo] = []
        self._total   = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._popup = NotificationPopup()
        self._popup.start()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            print("⚠️  Capture is already running.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("🚀 Capture started  (Ctrl+C to stop)")
        print(f"   Interval: {self.interval_min}–{self.interval_max} seconds at random")

    def stop(self):
        self._running = False
        self._popup.stop()
        if self._thread:
            self._thread.join(timeout=3)
        print(f"\n🛑 Capture stopped  —  {self._total} screenshots uploaded.")

    # ── capture loop ──────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            delay = random.randint(self.interval_min, self.interval_max)
            print(f"⏳ Next capture in {delay}s …")
            for _ in range(delay):
                if not self._running:
                    return
                time.sleep(1)
            if self._running:
                self.capture()

    # ── single capture ────────────────────────────────────────────────────────

    def capture(self, annotation: str = "") -> Optional[ScreenshotInfo]:
        """
        Take one screenshot (optionally annotated), upload to Supabase,
        and record metadata in-memory.

        Parameters
        ----------
        annotation : str
            Text to overlay on the screenshot (bottom-left). Empty = none.

        Returns
        -------
        ScreenshotInfo or None on failure.
        """
        try:
            raw: Image.Image = pyautogui.screenshot()
            w, h = raw.size
            ts = datetime.now()
            ts_str = ts.strftime("%Y%m%d_%H%M%S")

            if annotation:
                raw = self._annotate(raw, annotation)

            # Encode to bytes in-memory
            buf = io.BytesIO()
            if self.compress and not annotation:
                filename = f"screenshot_{ts_str}.jpg"
                raw.save(buf, "JPEG", optimize=True, quality=self.quality)
            else:
                filename = f"screenshot_{ts_str}.png"
                raw.convert("RGB").save(buf, "PNG")

            image_bytes = buf.getvalue()
            size_kb = round(len(image_bytes) / 1024, 2)

            info = ScreenshotInfo(
                timestamp=ts.isoformat(),
                filename=filename,
                width=w,
                height=h,
                size_kb=size_kb,
            )

            # Upload (non-blocking on failure)
            info.public_url = self._upload(info, image_bytes)

            # Store in-memory history
            self._screenshots.append(info)
            if len(self._screenshots) > self.max_history:
                self._screenshots = self._screenshots[-self.max_history:]
            self._total += 1

            print(f"✅ [{ts.strftime('%H:%M:%S')}]  {filename}  ({size_kb} KB)"
                  f"  {w}×{h}")

            self._popup.notify()
            return info

        except Exception as exc:
            print(f"❌ Capture error: {exc}")
            return None

    # ── annotation helper ─────────────────────────────────────────────────────

    @staticmethod
    def _annotate(img: Image.Image, text: str) -> Image.Image:
        """Overlay semi-transparent text banner at bottom-left."""
        rgba = img.convert("RGBA")
        draw = ImageDraw.Draw(rgba)
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except Exception:
            font = ImageFont.load_default()

        bbox   = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = 10
        x = margin
        y = rgba.height - th - margin * 2

        overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle(
            [x, y, x + tw + margin * 2, y + th + margin * 2],
            fill=(0, 0, 0, 140),
        )
        combined = Image.alpha_composite(rgba, overlay)
        ImageDraw.Draw(combined).text((x + margin, y + margin),
                                      text, fill=(255, 255, 255), font=font)
        return combined

    # ── Supabase upload ───────────────────────────────────────────────────────

    def _upload(self, info: ScreenshotInfo, data: bytes) -> Optional[str]:
        """Upload bytes to Storage and insert metadata row. Returns public URL."""
        sb = _supabase_client()
        if sb is None:
            return None

        storage_path = f"{DEVELOPER_ID}/{info.filename}"
        mime = "image/jpeg" if info.filename.endswith(".jpg") else "image/png"

        # 1. Storage upload
        try:
            sb.storage.from_(STORAGE_BUCKET).upload(
                path=storage_path,
                file=data,
                file_options={"content-type": mime},
            )
        except Exception as exc:
            print(f"   ❌ Storage upload failed: {exc}")
            return None

        # 2. Public URL
        try:
            public_url = sb.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
        except Exception:
            public_url = None

        # 3. Metadata row
        try:
            sb.table(METADATA_TABLE).insert({
                "user_id":      DEVELOPER_ID,
                "email":        DEVELOPER_EMAIL,
                "filename":     info.filename,
                "storage_path": storage_path,
                "public_url":   public_url,
                "width":        info.width,
                "height":       info.height,
                "size_kb":      info.size_kb,
                "timestamp":    info.timestamp,
                "app_active":   info.app_active,
            }).execute()
            print(f"   ☁️  Uploaded → {storage_path}")
        except Exception as exc:
            print(f"   ❌ Metadata insert failed: {exc}")

        return public_url

    # ── stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        total_kb = sum(s.size_kb for s in self._screenshots)
        return {
            "total_captured": self._total,
            "history_count":  len(self._screenshots),
            "total_size_kb":  round(total_kb, 2),
            "capture_active": self._running,
            "last_capture":   self._screenshots[-1].timestamp if self._screenshots else None,
        }

    def recent(self, n: int = 5) -> List[ScreenshotInfo]:
        return self._screenshots[-n:]

    def print_summary(self):
        s = self.stats()
        print("\n" + "=" * 52)
        print("  📊  CAPTURE SUMMARY")
        print("=" * 52)
        print(f"  Total uploaded : {s['total_captured']}")
        print(f"  In history     : {s['history_count']}")
        print(f"  Total size     : {s['total_size_kb']:.1f} KB")
        print(f"  Status         : {'ACTIVE' if s['capture_active'] else 'STOPPED'}")
        if self._screenshots:
            print("\n  Recent captures:")
            for i, ss in enumerate(self.recent(5), 1):
                t = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
                print(f"    {i}. [{t}]  {ss.filename}  ({ss.size_kb} KB)")
        print("=" * 52 + "\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  📸  RANDOM-INTERVAL SCREENSHOT CAPTURE  →  SUPABASE")
    print("=" * 60)
    print(f"  Developer : {DEVELOPER_ID}")
    print(f"  Bucket    : {STORAGE_BUCKET}")
    print(f"  Table     : {METADATA_TABLE}")
    print("  Interval  : 1 – 60 seconds (random)")
    print("  Storage   : In-memory only (no local files)")
    print("=" * 60)

    capture = ScreenshotCapture(
        interval_min=1,
        interval_max=60,
        compress=True,
        quality=85,
    )
    capture.start()

    print("  Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        capture.print_summary()
        print("✅  Goodbye!\n")


if __name__ == "__main__":
    main()