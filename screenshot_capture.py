

from __future__ import annotations

import io
import json
import os
import queue
import random
import threading
import time
import logging
from screenshot_outbox import ScreenshotOutbox
from screenshot_upload import upload_capture
from screenshot_limits import MAX_SCREENSHOT_BYTES, MAX_SCREENSHOT_DIMENSION
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Optional

import pyautogui
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from notification_popup import notify_screenshot_captured

# Load .env from the same directory as this script — works regardless of
# where the process is launched from.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)

# ── Environment ───────────────────────────────────────────────────────────────

import uuid as _uuid
import supabase_session

SUPABASE_URL       = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY       = os.getenv("SUPABASE_KEY", "").strip()
DEVELOPER_EMAIL    = os.getenv("DEVELOPER_EMAIL", "unknown").strip()

# DEVELOPER_USERNAME : plain string — used only as the Storage folder name
# DEVELOPER_ID       : must be a valid UUID — stored in the `developer_id` uuid column
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "developer").strip()
_raw_dev_id        = os.getenv("DEVELOPER_ID", "").strip()

try:
    DEVELOPER_ID = str(_uuid.UUID(_raw_dev_id))   # validated UUID string
except (ValueError, AttributeError):
    DEVELOPER_ID = None                            # will print a clear error at startup

# THE `monitoring` BUCKET, NOT `screenshots`.
#
# Two reasons, and either on its own would be enough:
#
#  1. The website only signs URLs for objects whose path is in `monitoring`
#     (`isPrivateScreenshot` in src/utils/screenshotFiles.js). An upload to
#     `screenshots` produces a row the dashboard cannot render now that the
#     bucket is private — it falls back to a stored public URL that no longer
#     resolves.
#  2. `monitoring` is the only bucket with storage policies written for it
#     (database/019_storage_hardening.sql). They key on the leading folder
#     being the organization, which is why the path below changed shape too.
#
# The metadata TABLE is still `screenshots` — only the bucket moved.
STORAGE_BUCKET = "monitoring"
METADATA_TABLE = "screenshots"

# ── Startup environment check ─────────────────────────────────────────────────

def _check_env():
    
    ok = True
    
    

    if DEVELOPER_ID:
        print(f"  {'DEVELOPER_ID':22s}: ✅ {DEVELOPER_ID}")
    else:
        ok = False

    print("─" * 60)
    return ok

# ─────────────────────────────────────────────────────────────────────────────


def _supabase_client():
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        
        return None
    from supabase import create_client
    # Ensure URL has trailing slash to avoid storage endpoint warning
    url = SUPABASE_URL if SUPABASE_URL.endswith('/') else SUPABASE_URL + '/'
    client = create_client(url, SUPABASE_KEY)
    # Authorize storage + postgrest as the signed-in user (RLS/anon key).
    try:
        import supabase_session
        supabase_session.register(client)
    except Exception:
        pass
    return client


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
    annotation_text: Optional[str] = None


class ScreenshotCapture:
    def __init__(
        self,
        interval_min: int = 1,
        interval_max: int = 60,
        compress:     bool = True,
        quality:      int  = 85,
        max_history:  int  = 200,
        developer_id:       Optional[str] = None,
        developer_email:    Optional[str] = None,
        developer_username: Optional[str] = None,
        pause_ctrl:          Optional[object] = None,
    ):
        self._tracking_context = supabase_session.tracking_context()
        self.interval_min = interval_min
        self.interval_max = interval_max
        self.compress     = compress
        self.quality      = quality
        self.max_history  = max_history

        # Dynamic user identity — falls back to module-level .env globals
        self._developer_id       = developer_id       or DEVELOPER_ID
        self._developer_email    = developer_email    or DEVELOPER_EMAIL
        self._developer_username = developer_username or DEVELOPER_USERNAME

        # Optional shared PauseController (pause_controller.PauseController).
        # When provided, this capture loop will block during pause and will not
        # upload/save any data while paused.
        self.pause_ctrl = pause_ctrl

        self._screenshots: List[ScreenshotInfo] = []
        self._total   = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._capture_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._sync_status = dict(pending=0, pending_bytes=0, last_success_at=None, error=None)
        self._outbox = None
        try:
            from config import user_data_dir
            if not self._tracking_context or self._tracking_context[2] != self._developer_id:
                raise ValueError("Screenshot identity unavailable")
            self._outbox = ScreenshotOutbox(user_data_dir(), SUPABASE_URL, self._tracking_context[:4])
            self._update_sync_status()
        except Exception:
            self._sync_status['error'] = 'Local screenshot storage is unavailable'
            logging.getLogger(__name__).exception('Screenshot queue initialization failed')

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if not self._authorized() or not self._outbox:
            return
        if self._running:
            print("⚠️  Capture is already running.")
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        print(f"\n🛑 Capture stopped  —  {self._total} screenshots captured.")

    # ── capture loop ──────────────────────────────────────────────────────────

    def _loop(self):
        self._replay_pending()
        while self._running:
            if not self._wait_if_paused():
                return
            delay = random.randint(self.interval_min, self.interval_max)
            print(f"⏳ Next capture in {delay}s …")
            for _ in range(delay):
                if not self._running:
                    return
                if not self._wait_if_paused():
                    return
                if self._stop_event.wait(1):
                    return
            if self._running:
                self.capture()

    def _wait_if_paused(self) -> bool:
        """Block if paused; return False if the controller is stopped."""
        ctrl = getattr(self, "pause_ctrl", None)
        if ctrl is None:
            return True
        wait = getattr(ctrl, "wait_if_paused", None)
        if callable(wait):
            return bool(wait())
        return not bool(getattr(ctrl, "is_paused", False))

    # ── single capture ────────────────────────────────────────────────────────

    def _current_app(self) -> Optional[str]:
        """Best-effort friendly name of the currently-focused app.

        Returns None off-Windows or on any error, so it never breaks capture.
        Previously app_active was never set, so every row stored NULL.
        """
        try:
            from app_monitor import get_foreground_app
            raw = get_foreground_app()
            if not raw:
                return None
            try:
                from app_name_converter import AppNameConverter
                return AppNameConverter().convert(raw)
            except Exception:
                return raw
        except Exception:
            return None

    def _authorized(self):
        return bool(self._tracking_context and
                    supabase_session.tracking_context() == self._tracking_context)

    def _capture_allowed(self):
        return (self._running and self._authorized()
                and not bool(getattr(self.pause_ctrl, 'is_paused', False))
                and not bool(getattr(self.pause_ctrl, 'is_stopped', False)))

    def capture(self, annotation: str = "") -> Optional[ScreenshotInfo]:
        """Persist an authorized image before attempting either upload phase."""
        if not self._capture_allowed() or not self._capture_lock.acquire(blocking=False):
            return None
        try:
            if not self._capture_allowed():
                return None
            if self._sync_status['pending_bytes'] >= self._outbox.max_bytes:
                raise OSError('Screenshot queue full')
            raw: Image.Image = pyautogui.screenshot()
            if not self._capture_allowed():
                return None
            width, height = raw.size
            if not (0 < width <= MAX_SCREENSHOT_DIMENSION and 0 < height <= MAX_SCREENSHOT_DIMENSION):
                self._sync_status['error'] = 'Screenshot dimensions exceed supported limits; capture stopped'
                self._running = False
                return None
            timestamp = datetime.now().astimezone()
            capture_id = str(_uuid.uuid4())
            if annotation:
                raw = self._annotate(raw, annotation)
            buffer = io.BytesIO()
            if self.compress and not annotation:
                filename = f"capture_{capture_id}.jpg"
                raw.convert('RGB').save(buffer, 'JPEG', optimize=True, quality=self.quality)
            else:
                filename = f"capture_{capture_id}.png"
                raw.convert('RGB').save(buffer, 'PNG')
            data = buffer.getvalue()
            if len(data) > MAX_SCREENSHOT_BYTES:
                self._sync_status['error'] = 'Screenshot exceeds the 6 MiB upload limit; capture stopped'
                self._running = False
                return None
            info = ScreenshotInfo(timestamp=timestamp.isoformat(), filename=filename,
                                  width=width, height=height, size_kb=round(len(data)/1024, 2),
                                  app_active=self._current_app(), annotation_text=annotation or None)
            if not self._capture_allowed():
                return None
            org, developer = self._tracking_context[1:3]
            metadata = dict(organization_id=org, developer_id=developer,
                            developer_email=self._developer_email, filename=filename,
                            storage_path=f'{org}/{developer}/{filename}', public_url=None,
                            width=width, height=height, size_kb=info.size_kb,
                            mime_type='image/jpeg' if filename.endswith('.jpg') else 'image/png',
                            app_active=info.app_active, is_annotated=bool(annotation),
                            annotation_text=info.annotation_text, timestamp=info.timestamp)
            self._outbox.put(capture_id, metadata, data)
            self._update_sync_status()
            self._screenshots.append(info)
            self._screenshots = self._screenshots[-self.max_history:]
            self._total += 1
            notify_screenshot_captured()
            self._replay_pending()
            return info
        except Exception:
            self._sync_status['error'] = 'Screenshot could not be saved; capture stopped'
            self._running = False
            self._stop_event.set()
            logging.getLogger(__name__).exception('Screenshot capture or local persistence failed')
            return None
        finally:
            self._capture_lock.release()

    def _update_sync_status(self):
        if self._outbox:
            count, size, recovery = self._outbox.usage()
            self._sync_status['pending'] = count
            self._sync_status['pending_bytes'] = size
            self._sync_status['error'] = ('A saved screenshot needs recovery' if recovery else
                                          'Screenshots are saved locally; upload will retry' if count else None)

    def _replay_pending(self):
        if not self._outbox or not self._capture_allowed():
            return
        try:
            uploaded = self._outbox.replay(
                lambda *args: upload_capture(SUPABASE_URL, SUPABASE_KEY, self._tracking_context,
                                             self._capture_allowed, *args), self._capture_allowed)
            if uploaded:
                self._sync_status['last_success_at'] = datetime.now().astimezone().isoformat()
            self._update_sync_status()
        except Exception:
            self._sync_status['error'] = 'Screenshot synchronization needs attention'
            logging.getLogger(__name__).exception('Screenshot replay failed; bytes retained')

    def get_sync_status(self):
        return dict(self._sync_status)

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

    def get_stats(self) -> dict:
        """Alias for stats() — used by TimerTracker/dashboard."""
        return self.stats()

    def recent(self, n: int = 5) -> List[ScreenshotInfo]:
        return self._screenshots[-n:]

    def print_summary(self):
        s = self.stats()
        if self._screenshots:
            for i, ss in enumerate(self.recent(5), 1):
                t = datetime.fromisoformat(ss.timestamp).strftime("%H:%M:%S")
                # Intentionally minimal: avoid changing console behaviour
        


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
 

    if not _check_env():
        
        return

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